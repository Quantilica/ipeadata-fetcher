"""Tests for ipeadata-fetcher Typer plugin."""

from typer.testing import CliRunner

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


def test_cli_backfill(tmp_path, monkeypatch) -> None:
    """Test quantilica ipeadata backfill."""
    runner = CliRunner()
    executed = []

    monkeypatch.setattr(
        "ipeadata_fetcher.plugin._get_backfill_units",
        lambda: ["PRECOS_IPCAG", "BM12_TJOVER12"],
    )
    monkeypatch.setattr(
        "ipeadata_fetcher.plugin._run_backfill_unit",
        lambda unit: executed.append(unit),
    )

    result = runner.invoke(app, ["backfill", "-o", str(tmp_path)])
    assert result.exit_code == 0
    assert executed == ["PRECOS_IPCAG", "BM12_TJOVER12"]
