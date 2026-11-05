"""Backfill: incremental por SERATUALIZACAO, série vazia e pool limitado (offline)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from typer.testing import CliRunner

from ipeadata_fetcher import backfill, catalog
from ipeadata_fetcher.client import IpeadataClient
from ipeadata_fetcher.constants import ODATA_HOST
from ipeadata_fetcher.plugin import app

TODAY = "20261103"


def _meta(code: str, stamp: str | None) -> dict:
    row = {"SERCODIGO": code, "SERNOME": code, "BASNOME": "Macroeconômico"}
    if stamp:
        row["SERATUALIZACAO"] = stamp
    return row


class FakeOData:
    """Responde ``ValoresSerie`` de uma fixture; registra chamadas e concorrência."""

    def __init__(self, values: dict[str, list], *, delay: float = 0.0) -> None:
        self.values = values
        self.delay = delay
        self.calls: list[str] = []
        self.live = 0
        self.peak = 0
        self._lock = threading.Lock()

    def download_resource(self, url: str, dest: Path, *args, **kw) -> None:
        code = url.split("SERCODIGO='")[1].split("'")[0]
        with self._lock:
            self.calls.append(code)
            self.live += 1
            self.peak = max(self.peak, self.live)
        try:
            time.sleep(self.delay)
            if code not in self.values:
                raise RuntimeError("HTTP 500")
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_text(json.dumps({"value": self.values[code]}))
        finally:
            with self._lock:
                self.live -= 1


def test_so_rebaixa_serie_cuja_atualizacao_mudou(tmp_path: Path) -> None:
    rows = [{"VALDATA": "2024-01-01", "VALVALOR": 1.0}]
    api = FakeOData({"A": rows, "B": rows, "C": rows})
    series = [_meta("A", "2026-01-01"), _meta("B", "2026-01-01"), _meta("C", None)]

    r1 = backfill.run_backfill(series, api, tmp_path, today=TODAY)
    assert sorted(r1.downloaded) == ["A", "B", "C"] and not r1.errors

    api.calls.clear()
    series[1] = _meta("B", "2026-02-02")  # B foi atualizada na fonte
    r2 = backfill.run_backfill(series, api, tmp_path, today="20261104")
    assert sorted(api.calls) == ["B", "C"]  # C nao tem data: sempre rebaixa
    assert r2.unchanged == ["A"]
    state = json.loads((tmp_path / backfill.STATE_NAME).read_text())
    assert state == {"A": "2026-01-01", "B": "2026-02-02"}

    api.calls.clear()  # --restart ignora o estado
    backfill.run_backfill(series, api, tmp_path, today="20261105", resume=False)
    assert sorted(api.calls) == ["A", "B", "C"]


def test_serie_vazia_e_erro_contado_e_nao_entra_no_estado(tmp_path: Path) -> None:
    api = FakeOData({"OK": [{"VALVALOR": 1}], "VAZIA": []})
    series = [_meta("OK", "x1"), _meta("VAZIA", "x2")]
    rep = backfill.run_backfill(series, api, tmp_path, today=TODAY)
    assert rep.empty == ["VAZIA"] and rep.errors == 1
    assert not (tmp_path / f"VAZIA@{TODAY}.json").exists()
    assert (tmp_path / f"OK@{TODAY}.json").exists()
    assert json.loads((tmp_path / backfill.STATE_NAME).read_text()) == {"OK": "x1"}
    # na proxima rodada a vazia e tentada de novo
    api.calls.clear()
    backfill.run_backfill(series, api, tmp_path, today=TODAY)
    assert api.calls == ["VAZIA"]


def test_falha_de_uma_serie_nao_derruba_a_carga(tmp_path: Path) -> None:
    api = FakeOData({"A": [{"v": 1}]})
    rep = backfill.run_backfill(
        [_meta("A", "1"), _meta("QUEBRA", "1")], api, tmp_path, today=TODAY
    )
    assert rep.downloaded == ["A"]
    assert "QUEBRA" in rep.failed and "HTTP 500" in rep.failed["QUEBRA"]


def test_pool_respeita_o_limite_de_workers(tmp_path: Path) -> None:
    codes = [f"S{i}" for i in range(12)]
    api = FakeOData({c: [{"v": 1}] for c in codes}, delay=0.03)
    rep = backfill.run_backfill(
        [_meta(c, "1") for c in codes], api, tmp_path, today=TODAY, workers=3
    )
    assert len(rep.downloaded) == 12
    assert 1 < api.peak <= 3  # paralelo, mas nunca acima do limite


def test_cliente_com_workers_aplica_hostpolicy() -> None:
    policy = IpeadataClient(workers=3).client.host_policies[ODATA_HOST]
    assert policy.max_concurrency == 3
    assert policy.min_interval > 0 and policy.deadline
    assert ODATA_HOST not in IpeadataClient().client.host_policies


def test_cli_backfill_incremental_e_exit_code(monkeypatch, tmp_path: Path) -> None:
    series = [_meta("A", "t1"), _meta("VAZIA", "t1")]
    monkeypatch.setattr(catalog, "_fetch_all_series", lambda: series)
    api = FakeOData({"A": [{"v": 1}], "VAZIA": []})
    monkeypatch.setattr(
        IpeadataClient,
        "download_resource",
        lambda self, url, dest, **kw: api.download_resource(url, dest),
    )
    runner = CliRunner()
    args = ["backfill", "--all", "-o", str(tmp_path), "--workers", "2"]
    r1 = runner.invoke(app, args)
    assert r1.exit_code == 1  # serie vazia e erro
    assert "1 baixada(s)" in r1.output and "1 vazia(s)" in r1.output
    api.calls.clear()
    r2 = runner.invoke(app, args)
    assert api.calls == ["VAZIA"]  # A nao mudou: nao foi rebaixada
    assert "1 sem mudança" in r2.output
