"""Tests for ipeadata-fetcher Typer plugin."""

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
            {"SERCODIGO": "SERIE_A", "SERNOME": "Serie A", "BASNOME": "Macroeconômico", "TEMCODIGO": 1, "FONTE": "Fonte1"},
            {"SERCODIGO": "SERIE_B", "SERNOME": "Serie B", "BASNOME": "Social", "TEMCODIGO": 2, "FONTE": "Fonte2"},
            {"SERCODIGO": "SERIE_C", "SERNOME": "Serie C", "BASNOME": "Regional", "TEMCODIGO": 1, "FONTE": "Fonte1"},
        ]

    monkeypatch.setattr(catalog, "_fetch_all_series", fake_fetch_all)

    # Mock download to track calls
    from ipeadata_fetcher.client import IpeadataClient
    orig_download = IpeadataClient.download_resource

    def mock_download(self, url, dest, *, manifest_path=None):
        executed.append(url)

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