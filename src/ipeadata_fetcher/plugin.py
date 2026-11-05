"""Typer plugin for quantilica-cli integration."""

from __future__ import annotations

import contextvars
import datetime as dt
import functools
import inspect
import os
import typing
from pathlib import Path
from typing import Any

import typer
from quantilica.cli.sdk import CheckPlanItem, FetcherApp, make_resolve_groups
from quantilica.cli.ui import get_console
from quantilica.core.sync import FreshnessPolicy

from .backfill import run_backfill
from .catalog import GROUP_ALIASES, GROUPS, is_ativa
from .catalog import list_datasets as _catalog_list_datasets
from .client import IpeadataClient
from .storage import DataRepository

# O SDK espera ``alias -> lista de grupos``; passar a string crua faria ``list("all")``
# virar ['a', 'l', 'l'] ("Grupo desconhecido: 'a'").
ALIASES: dict[str, list[str]] = {
    alias: [canon] for alias, canon in GROUP_ALIASES.items()
}
resolve_groups = make_resolve_groups(GROUPS, ALIASES)


# ``--somente-ativas`` chega ao ``list_datasets`` (chamado pelo SDK só com o grupo)
# por uma variável de contexto, definida durante o comando.
_SOMENTE_ATIVAS: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ipeadata_somente_ativas", default=False
)


def list_datasets(group: str | None = None) -> list[dict[str, Any]]:
    """Catálogo do grupo, sem as séries inativas se ``--somente-ativas``."""
    return _catalog_list_datasets(group, somente_ativas=_SOMENTE_ATIVAS.get())


def _stamp_from_entry(entry: dict[str, Any]) -> dt.date | None:
    """Data de versão da série (``SERATUALIZACAO``), se disponível.

    O OData do Ipeadata não responde ``HEAD``; sem este carimbo o caminho cairia
    na data de hoje e o modo plano Postgres nunca casaria a versão, forçando
    re-download diário das ~4 mil séries.
    """
    raw = entry.get("seratualizacao")
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(str(raw)).date()
    except (TypeError, ValueError):
        return None


def path_builder(
    output_dir: Path, entry: dict[str, Any], last_modified: dt.date | None
) -> Path:
    """Build local storage path for a dataset entry."""
    stamp = _stamp_from_entry(entry) or last_modified
    return DataRepository(output_dir).path_for_entry(entry, last_modified=stamp)


fetcher = FetcherApp(
    name="ipeadata",
    help="Séries econômicas, sociais e regionais do Ipeadata",
    groups_dict=GROUPS,
    aliases_dict=ALIASES,
    list_datasets=list_datasets,
    path_builder=path_builder,
    default_output=Path("/data/ipeadata"),
    freshness_policy=FreshnessPolicy.REMOTE_ONLY,
)


def _ipeadata_check_entry(entry: dict[str, Any], output_dir: Path) -> CheckPlanItem:
    """Veredito de frescor sem rede (o plano Postgres decide o skip).

    O OData do Ipeadata não responde ``HEAD`` (404) e tem ~4 mil séries: sondar
    cada uma no ``check`` levava mais de 20 min. O veredito local (arquivo ou
    sidecar presente) mantém o ``check`` barato; com ``CRON_PLAN_MODE=postgres``
    o plano em ``ingest.file_version`` reclassifica cada item para ``skip``.
    """
    dataset = str(entry.get("group") or "series")
    eid = str(entry.get("id", "unknown"))
    local = path_builder(output_dir, entry, None)
    sidecar = local.with_name(local.name + ".manifest.json")
    exists = local.exists() or sidecar.exists()
    return CheckPlanItem(
        dataset=dataset,
        id=eid,
        url=str(entry.get("url", "")),
        partition=str(entry.get("tema")) if entry.get("tema") is not None else None,
        local_path=str(local),
        remote_etag=None,
        remote_last_modified=None,
        remote_size=None,
        local_exists=exists,
        action="skip-up-to-date" if exists else "download",
        reason="local-exists" if exists else "not-probed",
        entry=dict(entry),
    )


fetcher.check_entry = _ipeadata_check_entry  # type: ignore[method-assign]


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
        raise ImportError(
            "Conversão para o lake requer o extra 'analysis'. "
            "Instale com: quantilica install ipeadata --extra analysis"
        ) from exc
    return lake.converter.convert(input_dir, lake_dir, datasets=dataset, force=force)


def _add_somente_ativas(command_name: str) -> None:
    """Acrescenta ``--somente-ativas`` ao comando ``command_name`` do SDK."""
    info = next(
        c
        for c in fetcher.app.registered_commands
        if c.callback.__name__ == command_name
    )
    original = info.callback
    # As anotações do SDK são strings (``from __future__ import annotations``) e
    # só resolvem nos globais dele: resolve-as aqui para o Typer não as perder.
    hints = typing.get_type_hints(original, include_extras=True)
    sig = inspect.signature(original)
    sig = sig.replace(
        parameters=[
            p.replace(annotation=hints.get(p.name, p.annotation))
            for p in sig.parameters.values()
        ],
        return_annotation=inspect.Signature.empty,
    )
    option = inspect.Parameter(
        "somente_ativas",
        inspect.Parameter.KEYWORD_ONLY,
        default=typer.Option(
            False,
            "--somente-ativas",
            help="Ignora as séries inativas (SERSTATUS diferente de A); "
            "padrão: baixa todas",
        ),
        annotation=bool,
    )

    @functools.wraps(original)
    def wrapper(*args: Any, somente_ativas: bool = False, **kwargs: Any) -> Any:
        token = _SOMENTE_ATIVAS.set(somente_ativas)
        try:
            return original(*args, **kwargs)
        finally:
            _SOMENTE_ATIVAS.reset(token)

    del wrapper.__wrapped__  # o Typer deve ver a assinatura nova, não a original
    wrapper.__signature__ = sig.replace(  # type: ignore[attr-defined]
        parameters=[*sig.parameters.values(), option]
    )
    wrapper.__annotations__ = {
        **{k: v for k, v in hints.items() if k != "return"},
        "somente_ativas": bool,
    }
    info.callback = wrapper


_add_somente_ativas("sync")
_add_somente_ativas("check")

fetcher.command_convert(convert)
fetcher.command_pipeline(convert)


# Backfill command with filtering options
_backfill_options = {
    "regional": typer.Option(False, "--regional", help="Apenas séries regionais"),
    "base": typer.Option(None, "--base", help="Filtrar por base"),
    "theme": typer.Option(None, "--theme", help="Filtrar por tema (TEMCODIGO)"),
    "source": typer.Option(None, "--source", help="Filtrar por fonte"),
    "all_bases": typer.Option(False, "--all", help="Todas as bases"),
    "somente_ativas": typer.Option(
        False,
        "--somente-ativas",
        help="Ignora as séries inativas (SERSTATUS diferente de A)",
    ),
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
    somente_ativas: bool = _backfill_options["somente_ativas"],
    output: Path | None = typer.Option(None, "--output", "-o"),  # noqa: B008
    resume: bool = typer.Option(  # noqa: B008
        True,
        "--resume/--restart",
        help="--resume rebaixa só séries cuja SERATUALIZACAO mudou; "
        "--restart rebaixa tudo",
    ),
    workers: int = typer.Option(  # noqa: B008
        3, "--workers", min=1, help="Downloads simultâneos (limite por host)"
    ),
    verbose: bool = typer.Option(False, "--verbose"),  # noqa: B008
) -> None:
    """Carga histórica exaustiva de séries do Ipeadata (JSON)."""
    from ipeadata_fetcher.catalog import _fetch_all_series

    console = get_console()

    def say(message: str) -> None:
        # Texto dinâmico (códigos, mensagens de erro): sem interpretar markup.
        console.print(message, markup=False, highlight=False, soft_wrap=True)

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
        all_series = [
            s for s in all_series if (s.get("FNTSIGLA") or s.get("FONTE")) == source
        ]

    # Sem filtros explícitos: todas as séries (exaustivo). `--all` fica
    # redundante e é mantido só por compatibilidade.
    all_series = [s for s in all_series if "SERCODIGO" in s]
    if somente_ativas:
        all_series = [s for s in all_series if is_ativa(s.get("SERSTATUS"))]
    if not all_series:
        say("Nenhuma série corresponde aos filtros.")
        raise typer.Exit(0)

    say(f"Verificando {len(all_series)} séries ({workers} workers)...")
    client = IpeadataClient(workers=workers)
    base_dir = output or (
        Path(os.environ.get("DATA_DIR", "~/data")).expanduser() / "ipeadata"
    )
    out_dir = base_dir / "series"
    today = dt.date.today().strftime("%Y%m%d")

    # Mesmo layout do `sync`: <grupo>/<SERCODIGO>@<SERATUALIZACAO>.json
    from ipeadata_fetcher.catalog import _series_to_entries

    entries_by_code = {e["id"]: e for e in _series_to_entries(all_series)}

    def _path_for(code: str) -> Path:
        return path_builder(base_dir, entries_by_code[code], None)

    report = run_backfill(
        all_series,
        client,
        out_dir,
        today=today,
        workers=workers,
        resume=resume,
        progress=say if verbose else None,
        path_for=_path_for,
    )
    say(
        f"Concluído: {len(report.downloaded)} baixada(s), "
        f"{len(report.unchanged)} sem mudança (SERATUALIZACAO), "
        f"{len(report.empty)} vazia(s), {len(report.failed)} falha(s)."
    )
    for code in report.empty:
        say(f"ERRO série vazia: {code}")
    for code, msg in report.failed.items():
        say(f"ERRO {code}: {msg}")
    if report.errors:
        raise typer.Exit(1)


app = fetcher.app
