"""Typer plugin for quantilica-cli integration."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from quantilica.cli.sdk import FetcherApp, make_resolve_groups

from .catalog import GROUP_ALIASES, GROUPS, list_datasets
from .client import IpeadataClient
from .constants import valores_serie_url
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
def _get_backfill_units(*, regional: bool = False) -> list[str]:
    """Return units for backfill: list of series codes."""
    if regional:
        return [e["id"] for e in list_datasets("regional")]
    return [e["id"] for e in list_datasets()]


def _run_backfill_unit(unit: str, output_dir: Path | None = None) -> None:
    """Download single series JSON with manifest."""
    client = IpeadataClient()
    base_dir = output_dir or Path("/data/ipeadata")
    out_dir = base_dir / "series"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().strftime("%Y%m%d")
    out_file = out_dir / f"{unit}@{today}.json"
    if not out_file.exists():
        url = valores_serie_url(unit)
        client.download_resource(url, out_file)


def _run_backfill_wrapper(unit: str, output_dir: Path | None = None) -> None:
    import inspect

    sig = inspect.signature(_run_backfill_unit)
    if len(sig.parameters) >= 2:
        _run_backfill_unit(unit, output_dir)
    else:
        _run_backfill_unit(unit)


fetcher.command_backfill(
    lambda: _get_backfill_units(),
    _run_backfill_wrapper,
    name="backfill",
    help="Carga histórica exaustiva de séries do Ipeadata (JSON)",
)

app = fetcher.app
