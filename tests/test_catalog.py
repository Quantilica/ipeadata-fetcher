"""Tests for ipeadata-fetcher catalog."""

import pytest

from ipeadata_fetcher import catalog
from ipeadata_fetcher.catalog import GROUP_ALIASES, GROUPS, list_datasets


@pytest.fixture(autouse=True)
def offline_metadados(monkeypatch: pytest.MonkeyPatch) -> None:
    """Metadados OData falsos: grupos dinâmicos (todas/macro_all...) sem rede."""
    series = [
        {"SERCODIGO": "A", "SERNOME": "A", "BASNOME": "Macroeconômico"},
        {"SERCODIGO": "B", "SERNOME": "B", "BASNOME": "Social"},
        {"SERCODIGO": "C", "SERNOME": "C", "BASNOME": "Regional"},
    ]
    monkeypatch.setattr(catalog, "_fetch_all_series", lambda: series)


def test_list_datasets_all() -> None:
    """Test listing all datasets."""
    datasets = list_datasets()
    assert isinstance(datasets, list)


def test_list_datasets_by_group() -> None:
    """Test listing datasets by valid and invalid group."""
    for group in GROUPS:
        entries = list_datasets(group)
        assert isinstance(entries, list)

    for alias in GROUP_ALIASES:
        entries = list_datasets(alias)
        assert isinstance(entries, list)

    with pytest.raises(ValueError, match="Grupo desconhecido"):
        list_datasets("grupo_inexistente_xyz")


def test_macro_all_matches_real_basnome() -> None:
    """BASNOME real é "Macroeconômico": macro_all vinha vazio ("macro" != ...)."""
    assert [e["id"] for e in list_datasets("macro_all")] == ["A"]
    assert [e["id"] for e in list_datasets("social_all")] == ["B"]
    assert [e["id"] for e in list_datasets("regional_all")] == ["C"]
    assert len(list_datasets("todas")) == 3


@pytest.mark.network
def test_metadados_live() -> None:
    """Contra o OData real do Ipeadata; só com ``pytest -m network``."""
    from ipeadata_fetcher.client import IpeadataClient

    assert len(IpeadataClient().get_metadados()) > 1000


def _com_status(monkeypatch: pytest.MonkeyPatch) -> None:
    series = [
        {
            "SERCODIGO": "A",
            "SERNOME": "A",
            "BASNOME": "Macroeconômico",
            "SERSTATUS": "A",
        },
        {
            "SERCODIGO": "I",
            "SERNOME": "I",
            "BASNOME": "Macroeconômico",
            "SERSTATUS": "I",
        },
        {"SERCODIGO": "X", "SERNOME": "X", "BASNOME": "Social", "SERSTATUS": None},
        {"SERCODIGO": "S", "SERNOME": "S", "BASNOME": "Social"},
        {"SERCODIGO": "L", "SERNOME": "L", "BASNOME": "Social", "SERSTATUS": " a "},
    ]
    monkeypatch.setattr(catalog, "_fetch_all_series", lambda: series)


def test_entries_carry_ativa_from_serstatus(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_status(monkeypatch)
    ativa = {e["id"]: e["ativa"] for e in list_datasets("todas")}
    # SERSTATUS "A" (qualquer caixa/espaço) ou ausente -> ativa; outro valor -> inativa.
    assert ativa == {"A": True, "I": False, "X": True, "S": True, "L": True}
    assert all(isinstance(v, bool) for v in ativa.values())


def test_somente_ativas_filters_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_status(monkeypatch)
    todas = {e["id"] for e in list_datasets("todas")}
    ativas = {e["id"] for e in list_datasets("todas", somente_ativas=True)}
    assert todas == {"A", "I", "X", "S", "L"}  # padrão: baixa tudo
    assert ativas == {"A", "X", "S", "L"}
    macro = list_datasets("macro_all", somente_ativas=True)
    assert {e["id"] for e in macro} == {"A"}
    # grupos core não têm SERSTATUS: continuam inteiros
    assert len(list_datasets("macro", somente_ativas=True)) == len(
        list_datasets("macro")
    )
