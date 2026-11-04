"""Tests for ipeadata-fetcher Typer plugin."""

from pathlib import Path

from typer.testing import CliRunner

from ipeadata_fetcher import catalog
from ipeadata_fetcher.plugin import app


def test_cli_list() -> None:
    """Test quantilica ipeadata list."""
    runner = CliRunner()
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "macro" in result.output
    assert "PRECOS_IPCAG" in result.output


def test_cli_convert_help() -> None:
    """Test quantilica ipeadata convert --help."""
    runner = CliRunner()
    result = runner.invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    assert "--lake" in result.output


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
