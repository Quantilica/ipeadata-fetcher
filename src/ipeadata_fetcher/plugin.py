"""Typer plugin for quantilica-cli integration."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

import typer
from quantilica.cli.sdk import FetcherApp, make_resolve_groups
from quantilica.core.sync import FreshnessPolicy

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
    freshness_policy=FreshnessPolicy.REMOTE_ONLY,
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


# Backfill command with filtering options
_backfill_options = {
    "regional": typer.Option(False, "--regional", help="Apenas séries regionais"),
    "base": typer.Option(None, "--base", help="Filtrar por base"),
    "theme": typer.Option(None, "--theme", help="Filtrar por tema (TEMCODIGO)"),
    "source": typer.Option(None, "--source", help="Filtrar por fonte"),
    "all_bases": typer.Option(False, "--all", help="Todas as bases"),
}


@fetcher.app.command(
    name="backfill",
    help="Carga histórica exaustiva de séries do Ipeadata (JSON)",
)
def _backfill_command(
    regional: bool = _backfill_options["regional"],
    base: str | None = _backfill_options["base"],
    theme: int | None = _backfill_options["theme"],
    source: str | None = _backfill_options["source"],
    all_bases: bool = _backfill_options["all_bases"],
    output: Path | None = typer.Option(None, "--output", "-o"),  # noqa: B008
    resume: bool = typer.Option(True, "--resume/--restart"),  # noqa: B008
    verbose: bool = typer.Option(False, "--verbose"),  # noqa: B008
) -> None:
    """Carga histórica exaustiva de séries do Ipeadata (JSON)."""
    from ipeadata_fetcher.catalog import _fetch_all_series, _series_to_entries

    all_series = _fetch_all_series()

    # Mapping from user-friendly base names to BASNOME values
    BASE_MAP = {
        "macro": "Macroeconômico",
        "social": "Social",
        "regional": "Regional",
    }

    if regional:
        all_series = [
            s for s in all_series if (s.get("BASNOME") or "").lower() == "regional"
        ]
    elif base:
        target_base = BASE_MAP.get(base.lower(), base)
        all_series = [
            s
            for s in all_series
            if (s.get("BASNOME") or "").lower() == target_base.lower()
        ]

    # Filter by theme and source (explicit filters)
    if theme is not None:
        all_series = [s for s in all_series if s.get("TEMCODIGO") == theme]
    if source:
        all_series = [s for s in all_series if s.get("FONTE") == source]

    # Default: only core series when no explicit filters
    if not (regional or base or theme is not None or source or all_bases):
        from ipeadata_fetcher.catalog import (
            CORE_MACRO_SERIES,
            CORE_REGIONAL_SERIES,
            CORE_SOCIAL_SERIES,
        )

        core_codes = {
            c[0] for c in CORE_MACRO_SERIES + CORE_SOCIAL_SERIES + CORE_REGIONAL_SERIES
        }
        all_series = [s for s in all_series if s.get("SERCODIGO") in core_codes]

    units = [e["id"] for e in _series_to_entries(all_series)]

    if not units:
        print("Nenhuma série corresponde aos filtros.")
        raise typer.Exit(0)

    print(f"Baixando {len(units)} séries...")
    client = IpeadataClient()  # noqa: E501
    base_dir = output or (
        Path(os.environ.get("DATA_DIR", "~/data")).expanduser() / "ipeadata"
    )
    out_dir = base_dir / "series"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().strftime("%Y%m%d")

    for i, unit in enumerate(units, 1):
        out_file = out_dir / f"{unit}@{today}.json"
        if resume and out_file.exists():
            if verbose:
                print(f"[{i}/{len(units)}] {unit} - pulando (já existe)")
            continue
        if verbose:
            print(f"[{i}/{len(units)}] {unit} - baixando...")
        url = valores_serie_url(unit)
        client.download_resource(url, out_file)

    print(f"Concluído: {len(units)} série(s).")


app = fetcher.app
