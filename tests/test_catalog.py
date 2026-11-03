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
