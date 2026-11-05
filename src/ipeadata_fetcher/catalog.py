"""Dataset catalog for ipeadata-fetcher."""

from __future__ import annotations

import unicodedata
from typing import Any

from ._catalog_base import DatasetEntry, GroupInfo, static_dataset
from .client import IpeadataClient
from .constants import (
    METADADOS_URL,
    PAISES_URL,
    TEMAS_URL,
    TERRITORIOS_URL,
    valores_serie_url,
)

__all__ = [
    "DatasetEntry",
    "GroupInfo",
    "GROUPS",
    "GROUP_ALIASES",
    "list_datasets",
    "list_all_series",
    "list_series_by_base",
    "is_ativa",
]

# Core series for backward compatibility / quick sync
CORE_MACRO_SERIES = [
    ("PRECOS_IPCAG", "IPCA Geral - Índice"),
    ("BM12_TJOVER12", "Taxa de Juros - Selic - Acumulada no Mês"),
    ("BM12_ERC12", "Taxa de Câmbio - R$ / US$ - Comercial - Venda - Média"),
    ("PIB_PIB", "PIB Nominal - Brasil"),
    ("IGP_IGPM", "IGP-M Geral - Índice"),
    ("INPC_INPC", "INPC Geral - Índice"),
    ("BM12_PIB12", "PIB Mensal - Bacen"),
]

CORE_SOCIAL_SERIES = [
    ("ADH_IDHM", "IDHM - Índice de Desenvolvimento Humano Municipal"),
    ("ADH_ESPVIDA", "Esperança de Vida ao Nascer"),
    ("PNAD_PO", "População Ocupada - PNAD"),
    ("PNAD_TD", "Taxa de Desocupação - PNAD"),
]

CORE_REGIONAL_SERIES = [
    ("DFEDUCM", "Despesa com Educação - Municípios - STN"),
    ("DFSAUDEM", "Despesa com Saúde - Municípios - STN"),
    ("NINVAG", "Operações de Crédito - Municípios - BCB"),
]


def _build_entries_for_series(
    group: str, series_list: list[tuple[str, str]]
) -> list[DatasetEntry]:
    return [
        DatasetEntry(
            id=code,
            base_id=code,
            name=name,
            url=valores_serie_url(code),
            ext="json",
            group=group,
            slug=code,
        )
        for code, name in series_list
    ]


def _build_dimensoes_entries() -> list[DatasetEntry]:
    return [
        static_dataset(
            "dimensoes",
            id="metadados",
            name="Catálogo de Metadados Ipeadata",
            url=METADADOS_URL,
            ext="json",
        ),
        static_dataset(
            "dimensoes",
            id="temas",
            name="Tabela de Temas Ipeadata",
            url=TEMAS_URL,
            ext="json",
        ),
        static_dataset(
            "dimensoes",
            id="territorios",
            name="Tabela de Territórios Ipeadata",
            url=TERRITORIOS_URL,
            ext="json",
        ),
        static_dataset(
            "dimensoes",
            id="paises",
            name="Tabela de Países Ipeadata",
            url=PAISES_URL,
            ext="json",
        ),
    ]


def _core_groups() -> dict[str, dict[str, Any]]:
    """Core groups (18 curated series) for quick daily sync."""
    return {
        "macro": GroupInfo(
            name="Séries Macroeconômicas (core)",
            entries=_build_entries_for_series("macro", CORE_MACRO_SERIES),
        ).to_dict(),
        "social": GroupInfo(
            name="Séries Sociais e Demográficas (core)",
            entries=_build_entries_for_series("social", CORE_SOCIAL_SERIES),
        ).to_dict(),
        "regional": GroupInfo(
            name="Séries Regionais e Municipais (core)",
            entries=_build_entries_for_series("regional", CORE_REGIONAL_SERIES),
        ).to_dict(),
        "dimensoes": GroupInfo(
            name="Dimensões e Metadados do Ipeadata",
            entries=_build_dimensoes_entries(),
        ).to_dict(),
    }


_CORE_GROUPS = _core_groups()
_ALL_SERIES_CACHE: list[dict[str, Any]] | None = None


def _fetch_all_series() -> list[dict[str, Any]]:
    """Fetch all 4000+ series from Ipeadata metadata endpoint."""
    global _ALL_SERIES_CACHE
    if _ALL_SERIES_CACHE is None:
        client = IpeadataClient()
        _ALL_SERIES_CACHE = client.get_metadados()
    return _ALL_SERIES_CACHE


def _base_group(basnome: str | None) -> str:
    """``BASNOME`` do OData ("Macroeconômico") -> grupo canônico (``macro``)."""
    folded = unicodedata.normalize("NFKD", basnome or "macro")
    folded = folded.encode("ascii", "ignore").decode("ascii").strip().lower()
    return "macro" if folded.startswith("macro") else folded


def is_ativa(serstatus: Any) -> bool:
    """``SERSTATUS`` do OData -> série ativa? ``A`` (qualquer caixa) ou ausente: sim."""
    status = str(serstatus).strip().upper() if serstatus is not None else ""
    return status in ("", "A")


def _series_to_entries(series_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw series metadata to catalog entries."""
    return [
        {
            "id": s["SERCODIGO"],
            "base_id": s["SERCODIGO"],
            "name": s["SERNOME"],
            "url": valores_serie_url(s["SERCODIGO"]),
            "ext": "json",
            "group": _base_group(s.get("BASNOME")),
            "slug": s["SERCODIGO"],
            "tema": s.get("TEMCODIGO"),
            "fonte": s.get("FNTSIGLA") or s.get("FONTE"),
            "unidade": s.get("UNINOME") or s.get("SERUNIDADE"),
            "periodicidade": s.get("PERNOME") or s.get("SERPERIODICIDADE"),
            "ativa": is_ativa(s.get("SERSTATUS")),
        }
        for s in series_list
        if "SERCODIGO" in s
    ]


def _only_active(
    entries: list[dict[str, Any]], somente_ativas: bool
) -> list[dict[str, Any]]:
    # Entradas sem ``ativa`` (grupos core, dimensões) contam como ativas.
    if not somente_ativas:
        return entries
    return [e for e in entries if e.get("ativa", True)]


def list_all_series(*, somente_ativas: bool = False) -> list[dict[str, Any]]:
    """Return all ~4000 series from Ipeadata metadata.

    Each entry has ``ativa`` (``SERSTATUS == "A"``). By default inactive series are
    kept; ``somente_ativas=True`` drops them.
    """
    return _only_active(_series_to_entries(_fetch_all_series()), somente_ativas)


def list_series_by_base(
    base: str, *, somente_ativas: bool = False
) -> list[dict[str, Any]]:
    """Filter series by base name (macro, social, regional)."""
    all_series = _fetch_all_series()
    # BASNOME real é "Macroeconômico"/"Social"/"Regional"; comparar pelo grupo
    # canônico (antes "macroeconômico" != "macro" e macro_all vinha vazio).
    wanted = _base_group(base)
    filtered = [s for s in all_series if _base_group(s.get("BASNOME")) == wanted]
    return _only_active(_series_to_entries(filtered), somente_ativas)


# Compatibilidade: catálogo padrão usa apenas as 18 séries core.
# Para sincronização completa, use `list_all_series()` ou `list_series_by_base()`.
# "all" incluído para que `resolve_groups` o reconheça; as entradas vêm de `list_all_series()`.
GROUPS: dict[str, dict[str, Any]] = _core_groups()
GROUPS["all"] = {"name": "Todas as séries do Ipeadata (exaustivo)", "entries": []}

GROUP_ALIASES: dict[str, str] = {
    "padrao": "macro",
    "macroeconomico": "macro",
    "sociais": "social",
    "regioes": "regional",
    "metadados": "dimensoes",
    "todas": "all",  # especial: todas as séries
    # Grupos dinâmicos (todas as séries de uma base): não estão em GROUPS porque
    # exigem consulta ao OData; entram como alias para valer em `sync`/`list`.
    "all": "all",
    "macro_all": "macro_all",
    "social_all": "social_all",
    "regional_all": "regional_all",
}


def list_datasets(
    group: str | None = None, *, somente_ativas: bool = False
) -> list[dict[str, Any]]:
    """List datasets for a group or all groups.

    Groups:
      - all: todas as ~4000 séries do Ipeadata (padrão)
      - macro, social, regional, dimensoes: core 18 séries (compatibilidade)
      - macro_all, social_all, regional_all: todas as séries da base

    Toda entrada de série traz ``ativa`` (``SERSTATUS == "A"``); com
    ``somente_ativas=True`` as inativas saem da lista (padrão: todas).
    """
    if group is None:
        return list_all_series(somente_ativas=somente_ativas)

    canon = GROUP_ALIASES.get(group, group)

    if canon == "all":
        return list_all_series(somente_ativas=somente_ativas)
    if canon in ("macro_all", "social_all", "regional_all"):
        return list_series_by_base(
            canon.removesuffix("_all"), somente_ativas=somente_ativas
        )

    if canon not in GROUPS:
        raise ValueError(f"Grupo desconhecido: {group!r}")
    return list(GROUPS[canon]["entries"])
