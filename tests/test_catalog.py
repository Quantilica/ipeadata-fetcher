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
    # dimensões não têm SERSTATUS: continuam inteiras
    assert len(list_datasets("dimensoes", somente_ativas=True)) == len(
        list_datasets("dimensoes")
    )


# --- Dimensões com caminho estável -------------------------------------------


def _dimensoes() -> list[dict]:
    from ipeadata_fetcher.catalog import list_datasets

    return list_datasets("dimensoes")


def test_dimensoes_tem_caminho_estavel_entre_dias(monkeypatch, tmp_path) -> None:
    import datetime as dt

    from ipeadata_fetcher import storage
    from ipeadata_fetcher.plugin import path_builder

    class FrozenDate(dt.date):
        current = dt.date(2026, 11, 6)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(storage.dt, "date", FrozenDate)
    entries = _dimensoes()
    assert {e["id"] for e in entries} == {"metadados", "temas", "territorios", "paises"}
    dia1 = [path_builder(tmp_path, e, None) for e in entries]
    FrozenDate.current = dt.date(2026, 12, 25)
    dia2 = [path_builder(tmp_path, e, None) for e in entries]
    assert dia1 == dia2
    assert {p.name for p in dia1} == {
        "metadados@20261105.json",
        "temas@20261105.json",
        "territorios@20261105.json",
        "paises@20261105.json",
    }
    assert all(p.parent == tmp_path / "dimensoes" for p in dia1)


def test_series_continuam_versionadas_por_seratualizacao(tmp_path) -> None:
    from ipeadata_fetcher.catalog import _series_to_entries
    from ipeadata_fetcher.plugin import path_builder

    (entry,) = _series_to_entries(
        [
            {
                "SERCODIGO": "X",
                "BASNOME": "Social",
                "SERATUALIZACAO": "2026-09-30T10:00:00.000-03:00",
            }
        ]
    )
    assert entry.get("fixed_stamp") is None
    assert (
        path_builder(tmp_path, entry, None) == tmp_path / "social" / "X@20260930.json"
    )


def test_check_das_dimensoes_vira_skip_quando_o_sidecar_existe(tmp_path) -> None:
    from ipeadata_fetcher.plugin import _ipeadata_check_entry, path_builder

    for entry in _dimensoes():
        before = _ipeadata_check_entry(entry, tmp_path)
        assert before.action == "download"
        local = path_builder(tmp_path, entry, None)
        local.parent.mkdir(parents=True, exist_ok=True)
        # o ingest apaga o dado e mantém o sidecar
        local.with_name(local.name + ".manifest.json").write_text("{}")
        after = _ipeadata_check_entry(entry, tmp_path)
        assert after.action == "skip-up-to-date"
        assert after.local_path == str(local)
