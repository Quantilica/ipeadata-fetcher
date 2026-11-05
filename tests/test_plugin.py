"""Tests for ipeadata-fetcher Typer plugin."""

import re
from pathlib import Path

from typer.testing import CliRunner

from ipeadata_fetcher import catalog
from ipeadata_fetcher.plugin import app


def test_cli_list() -> None:
    """Test quantilica ipeadata list."""
    runner = CliRunner()
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "all" in result.output
    assert "PRECOS_IPCAG" in result.output


def test_cli_convert_help() -> None:
    """Test quantilica ipeadata convert --help."""
    runner = CliRunner()
    result = runner.invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    assert "--lake" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)


def test_cli_backfill_filters(monkeypatch, tmp_path) -> None:
    """Test backfill command with filter options."""
    runner = CliRunner()
    executed = []

    # Mock the catalog to return a fixed list
    def fake_fetch_all():
        return [
            {
                "SERCODIGO": "SERIE_A",
                "SERNOME": "Serie A",
                "BASNOME": "Macroeconômico",
                "TEMCODIGO": 1,
                "FONTE": "Fonte1",
            },
            {
                "SERCODIGO": "SERIE_B",
                "SERNOME": "Serie B",
                "BASNOME": "Social",
                "TEMCODIGO": 2,
                "FONTE": "Fonte2",
            },
            {
                "SERCODIGO": "SERIE_C",
                "SERNOME": "Serie C",
                "BASNOME": "Regional",
                "TEMCODIGO": 1,
                "FONTE": "Fonte1",
            },
        ]

    monkeypatch.setattr(catalog, "_fetch_all_series", fake_fetch_all)

    # Mock download to track calls
    from ipeadata_fetcher.client import IpeadataClient

    def mock_download(self, url, dest, *, manifest_path=None):
        executed.append(url)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_text('{"value": [{"VALDATA": "2024-01-01", "VALVALOR": 1}]}')

    monkeypatch.setattr(IpeadataClient, "download_resource", mock_download)

    # Test with --base macro
    executed.clear()
    result = runner.invoke(app, ["backfill", "--base", "macro", "-o", str(tmp_path)])
    assert result.exit_code == 0
    assert len(executed) == 1
    assert "SERIE_A" in executed[0]

    # Test with --theme 1
    executed.clear()
    result = runner.invoke(app, ["backfill", "--theme", "1", "-o", str(tmp_path)])
    assert result.exit_code == 0
    assert len(executed) == 2  # SERIE_A and SERIE_C

    # Test with --all
    executed.clear()
    result = runner.invoke(app, ["backfill", "--all", "-o", str(tmp_path)])
    assert result.exit_code == 0
    assert len(executed) == 3


def _fake_series():
    return [
        {
            "SERCODIGO": "SERIE_A",
            "SERNOME": "Serie A",
            "BASNOME": "Macroeconômico",
            "TEMCODIGO": 1,
            "PERNOME": "Mensal",
            "FNTSIGLA": "IBGE",
        },
        {
            "SERCODIGO": "SERIE_B",
            "SERNOME": "Serie B",
            "BASNOME": "Social",
            "TEMCODIGO": 2,
            "PERNOME": "Anual",
            "FNTSIGLA": "IBGE",
        },
        {
            "SERCODIGO": "SERIE_C",
            "SERNOME": "Serie C",
            "BASNOME": "Regional",
            "TEMCODIGO": 1,
            "PERNOME": "Mensal",
            "FNTSIGLA": "STN",
        },
    ]


def test_sync_dynamic_groups_resolve_offline(monkeypatch, tmp_path) -> None:
    """Regressão D1: `sync todas --dry-run` estourava ValueError 'a' e
    `sync macro_all` dava "Grupo desconhecido"."""
    monkeypatch.setattr(catalog, "_fetch_all_series", _fake_series)
    runner = CliRunner()
    for group, expected in (
        ("todas", {"SERIE_A", "SERIE_B", "SERIE_C"}),
        ("all", {"SERIE_A", "SERIE_B", "SERIE_C"}),
        ("macro_all", {"SERIE_A"}),
        ("social_all", {"SERIE_B"}),
        ("regional_all", {"SERIE_C"}),
    ):
        result = runner.invoke(app, ["sync", group, "--dry-run", "-o", str(tmp_path)])
        assert result.exit_code == 0, (group, result.output, result.exception)
        assert all(code in result.output for code in expected), (group, result.output)


def test_sync_string_alias_is_not_split_in_chars(tmp_path) -> None:
    """`padrao` -> macro (alias string virava ['m','a','c','r','o'])."""
    result = CliRunner().invoke(
        app, ["sync", "padrao", "--dry-run", "-o", str(tmp_path)]
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert "PRECOS_IPCAG" in result.output


def test_entries_use_real_odata_metadata_fields(monkeypatch) -> None:
    monkeypatch.setattr(catalog, "_fetch_all_series", _fake_series)
    entries = {e["id"]: e for e in catalog.list_all_series()}
    assert entries["SERIE_A"]["group"] == "macro"
    assert entries["SERIE_A"]["periodicidade"] == "Mensal"
    assert entries["SERIE_C"]["fonte"] == "STN"


def test_backfill_escreve_pelo_console_do_sdk(monkeypatch, tmp_path) -> None:
    """A saída do ``backfill`` passa pelo console (sem ``print``) e sai com 0."""
    from ipeadata_fetcher.client import IpeadataClient

    monkeypatch.setattr(
        catalog,
        "_fetch_all_series",
        lambda: [{"SERCODIGO": "SERIE_A", "BASNOME": "Macroeconômico"}],
    )
    monkeypatch.setattr(
        IpeadataClient,
        "download_resource",
        lambda self, url, dest, *, manifest_path=None: (
            Path(dest).parent.mkdir(parents=True, exist_ok=True),
            Path(dest).write_text(
                '{"value": [{"VALDATA": "2024-01-01", "VALVALOR": 1}]}'
            ),
        ),
    )
    result = CliRunner().invoke(
        app, ["backfill", "--all", "--verbose", "-o", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Verificando 1 séries" in result.output
    assert "Concluído: 1 baixada(s)" in result.output


def _series_com_status():
    return [
        {
            "SERCODIGO": "SERIE_ATIVA",
            "SERNOME": "a",
            "BASNOME": "Macroeconômico",
            "SERSTATUS": "A",
            "PERNOME": "Mensal",
        },
        {
            "SERCODIGO": "SERIE_INATIVA",
            "SERNOME": "i",
            "BASNOME": "Macroeconômico",
            "SERSTATUS": "I",
            "PERNOME": "Mensal",
        },
    ]


def test_sync_somente_ativas(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(catalog, "_fetch_all_series", _series_com_status)
    runner = CliRunner()
    base = ["sync", "todas", "--dry-run", "-o", str(tmp_path)]
    padrao = runner.invoke(app, base)
    assert padrao.exit_code == 0, padrao.output
    assert "SERIE_ATIVA" in padrao.output and "SERIE_INATIVA" in padrao.output
    filtrado = runner.invoke(app, [*base, "--somente-ativas"])
    assert filtrado.exit_code == 0, filtrado.output
    assert "SERIE_ATIVA" in filtrado.output
    assert "SERIE_INATIVA" not in filtrado.output
    # a flag não vaza para a chamada seguinte
    assert "SERIE_INATIVA" in runner.invoke(app, base).output


def test_backfill_somente_ativas(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(catalog, "_fetch_all_series", _series_com_status)
    from ipeadata_fetcher.client import IpeadataClient

    baixadas: list[str] = []

    def fake_download(self, url, dest, *, manifest_path=None):
        baixadas.append(url)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_text('{"value": [{"VALDATA": "2024-01-01", "VALVALOR": 1}]}')

    monkeypatch.setattr(IpeadataClient, "download_resource", fake_download)
    runner = CliRunner()
    result = runner.invoke(
        app, ["backfill", "--all", "--somente-ativas", "-o", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert len(baixadas) == 1 and "SERIE_ATIVA" in baixadas[0]
