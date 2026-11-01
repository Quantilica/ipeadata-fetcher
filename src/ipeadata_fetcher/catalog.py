"""Dataset catalog for ipeadata-fetcher."""

from __future__ import annotations

from typing import Any

from ._catalog_base import DatasetEntry, GroupInfo, static_dataset
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
]

# Benchmark & prominent core series for initial catalog enumeration:
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


GROUPS: dict[str, dict[str, Any]] = {
    "macro": GroupInfo(
        name="Séries Macroeconômicas",
        entries=_build_entries_for_series("macro", CORE_MACRO_SERIES),
    ).to_dict(),
    "social": GroupInfo(
        name="Séries Sociais e Demográficas",
        entries=_build_entries_for_series("social", CORE_SOCIAL_SERIES),
    ).to_dict(),
    "regional": GroupInfo(
        name="Séries Regionais e Municipais",
        entries=_build_entries_for_series("regional", CORE_REGIONAL_SERIES),
    ).to_dict(),
    "dimensoes": GroupInfo(
        name="Dimensões e Metadados do Ipeadata",
        entries=_build_dimensoes_entries(),
    ).to_dict(),
}

GROUP_ALIASES: dict[str, str] = {
    "padrao": "macro",
    "macroeconomico": "macro",
    "sociais": "social",
    "regioes": "regional",
    "metadados": "dimensoes",
}


def list_datasets(group: str | None = None) -> list[dict[str, Any]]:
    """List datasets for a group or all groups."""
    if group is None:
        entries: list[dict[str, Any]] = []
        for g_data in GROUPS.values():
            entries.extend(g_data["entries"])
        return entries

    canon = GROUP_ALIASES.get(group, group)
    if canon not in GROUPS:
        raise ValueError(f"Grupo desconhecido: {group!r}")
    return list(GROUPS[canon]["entries"])
