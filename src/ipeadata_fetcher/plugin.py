"""Typer plugin for quantilica-cli integration."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from quantilica.cli.sdk import FetcherApp, make_resolve_groups

from .catalog import GROUP_ALIASES, GROUPS, list_datasets
from .client import IpeadataClient
from .storage import DataRepository

resolve_groups = make_resolve_groups(
    GROUPS, {alias: [canon] for alias, canon in GROUP_ALIASES.items()}
)


def path_builder(
    output_dir: Path, entry: dict[str, Any], last_modified: dt.date | None
) -> Path:
    """Build local storage path for a dataset entry."""
    return DataRepository(output_dir).path_for_entry(entry, last_modified=last_modified)


fetcher = FetcherApp(
    name="ipeadata",
    help="Séries econômicas, sociais e regionais do Ipeadata",
    groups_dict=GROUPS,
    aliases_dict=GROUP_ALIASES,
    list_datasets=list_datasets,
    path_builder=path_builder,
    default_output=Path("/data/ipeadata"),
)


def convert(
    input_dir: Path,
    lake_dir: Path,
    *,
    dataset: list[str] | None = None,
    force: bool = False,
) -> Any:
    """Converte arquivos brutos de ipeadata para o lake Hive (Parquet)."""
    try:
        from ipeadata_fetcher import lake
    except ImportError as exc:
        raise RuntimeError(
            "Conversão para o lake requer o extra 'analysis'. "
            "Instale com: quantilica install ipeadata --extra analysis"
        ) from exc
    return lake.converter.convert(input_dir, lake_dir, datasets=dataset, force=force)


fetcher.command_convert(convert)
fetcher.command_pipeline(convert)


# Register backfill subcommand (P5)
def _get_backfill_units() -> list[str]:
    """Return units for backfill: list of series codes."""
    return [e["id"] for e in list_datasets()]


def _run_backfill_unit(unit: str) -> None:
    """Download single series JSON."""
    client = IpeadataClient()
    out_dir = Path("/data/ipeadata/series")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().strftime("%Y%m%d")
    out_file = out_dir / f"{unit}@{today}.json"
    if not out_file.exists():
        data = client.get_valores_serie(unit)
        import json

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


fetcher.command_backfill(
    lambda: _get_backfill_units(),
    lambda u: _run_backfill_unit(u),
    name="backfill",
    help="Carga histórica exaustiva de séries do Ipeadata (JSON)",
)

app = fetcher.app
