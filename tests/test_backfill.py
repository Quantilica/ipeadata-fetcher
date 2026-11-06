"""Backfill: incremental por SERATUALIZACAO, série vazia e pool limitado (offline)."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest
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


# --- Estado concorrente-seguro e reconstrução (sem rede) ---------------------


def test_saves_simultaneos_nao_perdem_chaves(tmp_path: Path) -> None:
    state_path = tmp_path / backfill.STATE_NAME
    barrier = threading.Barrier(8)

    def writer(i: int) -> None:
        barrier.wait()
        for j in range(20):
            backfill.save_state(state_path, {f"W{i}_{j}": "2026-01-01"})

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    state = backfill.load_state(state_path)
    assert len(state) == 8 * 20  # cada gravador só tinha as próprias chaves
    assert not list(tmp_path.glob("*.tmp"))


def test_save_state_une_com_o_disco_e_vence_a_data_mais_recente(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / backfill.STATE_NAME
    backfill.save_state(
        state_path, {"A": "2026-02-01T00:00:00-03:00", "B": "2026-01-01T00:00:00-03:00"}
    )
    merged = backfill.save_state(
        state_path, {"A": "2026-01-01T00:00:00-03:00", "C": "2026-03-01T00:00:00-03:00"}
    )
    assert merged == {
        "A": "2026-02-01T00:00:00-03:00",  # o disco era mais novo
        "B": "2026-01-01T00:00:00-03:00",  # só no disco: mantido
        "C": "2026-03-01T00:00:00-03:00",
    }
    assert backfill.load_state(state_path) == merged


def test_segunda_carga_com_lock_aborta(tmp_path: Path) -> None:
    api = FakeOData({"A": [{"v": 1}]})
    with backfill.state_lock(tmp_path / backfill.STATE_NAME):
        try:
            backfill.run_backfill([_meta("A", "1")], api, tmp_path, today=TODAY)
        except backfill.StateLockedError as exc:
            assert "em andamento" in str(exc)
        else:  # pragma: no cover - falha do teste
            raise AssertionError("a segunda carga deveria abortar")
    assert api.calls == []  # nada foi baixado
    # liberado o lock, a carga roda normalmente
    rep = backfill.run_backfill([_meta("A", "1")], api, tmp_path, today=TODAY)
    assert rep.downloaded == ["A"]


class _FakeMsvcrt:
    """``msvcrt.locking`` de mentira: um lock por arquivo (inode), como no Windows."""

    LK_NBLCK, LK_UNLCK = 2, 0

    def __init__(self) -> None:
        self.held: set[int] = set()

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        key = os.fstat(fd).st_ino
        if mode == self.LK_UNLCK:
            self.held.discard(key)
        elif key in self.held:
            raise OSError(36, "Resource deadlock avoided")
        else:
            self.held.add(key)


def test_lock_sem_fcntl_usa_msvcrt(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeMsvcrt()
    monkeypatch.setattr(backfill, "fcntl", None)
    monkeypatch.setattr(backfill, "msvcrt", fake, raising=False)
    state = tmp_path / backfill.STATE_NAME
    with backfill.state_lock(state):
        with pytest.raises(backfill.StateLockedError), backfill.state_lock(state):
            pass  # pragma: no cover - o segundo lock deveria falhar
    assert fake.held == set()
    assert backfill.save_state(state, {"A": "1"}) == {"A": "1"}
    assert fake.held == set()


def test_cli_backfill_aborta_com_lock_ocupado(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(catalog, "_fetch_all_series", lambda: [_meta("A", "t1")])
    api = FakeOData({"A": [{"v": 1}]})
    monkeypatch.setattr(
        IpeadataClient,
        "download_resource",
        lambda self, url, dest, **kw: api.download_resource(url, dest),
    )
    state_path = tmp_path / "series" / backfill.STATE_NAME
    with backfill.state_lock(state_path):
        result = CliRunner().invoke(app, ["backfill", "-o", str(tmp_path)])
    assert result.exit_code == 2
    assert "em andamento" in result.output
    assert api.calls == []


def test_checkpoint_que_falha_nao_derruba_a_carga(monkeypatch, tmp_path: Path) -> None:
    """Disco que some no meio da carga (EIO): avisa, segue e grava no fim."""
    codes = [f"S{i}" for i in range(6)]
    api = FakeOData({c: [{"v": 1}] for c in codes})
    real_save = backfill.save_state
    calls = {"n": 0}

    def flaky_save(path: Path, state: dict) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(5, "Input/output error")
        return real_save(path, state)

    monkeypatch.setattr(backfill, "save_state", flaky_save)
    rep = backfill.run_backfill(
        [_meta(c, "1") for c in codes], api, tmp_path, today=TODAY, save_every=2
    )
    assert len(rep.downloaded) == 6
    assert rep.state_save_errors and "Input/output" in rep.state_save_errors[0]
    state = backfill.load_state(tmp_path / backfill.STATE_NAME)
    assert set(state) == set(codes)


def test_interrupcao_cancela_o_que_falta_baixar(monkeypatch, tmp_path: Path) -> None:
    codes = [f"S{i}" for i in range(30)]
    api = FakeOData({c: [{"v": 1}] for c in codes}, delay=0.01)
    seen = {"n": 0}

    def say(msg: str) -> None:
        seen["n"] += 1
        if seen["n"] == 2:
            raise KeyboardInterrupt

    try:
        backfill.run_backfill(
            [_meta(c, "1") for c in codes],
            api,
            tmp_path,
            today=TODAY,
            workers=1,
            progress=say,
        )
    except KeyboardInterrupt:
        pass
    assert len(api.calls) < len(codes)  # o resto da fila foi cancelado
    assert backfill.load_state(tmp_path / backfill.STATE_NAME)  # parcial gravado


def _canonical(base: Path, code: str, stamp: str) -> Path:
    from ipeadata_fetcher.catalog import _series_to_entries
    from ipeadata_fetcher.plugin import path_builder

    (entry,) = _series_to_entries([_meta(code, stamp)])
    return path_builder(base, entry, None)


def test_rebuild_state_com_sidecars_reconstroi_o_mapa_exato(tmp_path: Path) -> None:
    stamps = {
        "A": "2026-10-01T12:00:00.000-03:00",
        "B": "2026-10-02T08:30:00.000-03:00",
        "C": "2026-10-03T00:00:00.000-03:00",
        "D": "2026-10-04T00:00:00.000-03:00",
    }
    series = [_meta(c, s) for c, s in stamps.items()] + [_meta("SEM_DATA", None)]
    # A: só o sidecar (o ingest apagou o dado); B: o arquivo; C: sidecar de uma
    # versão antiga (outro carimbo) -> não conta; D: nada.
    a = _canonical(tmp_path, "A", stamps["A"])
    a.parent.mkdir(parents=True, exist_ok=True)
    a.with_name(a.name + ".manifest.json").write_text("{}")
    _canonical(tmp_path, "B", stamps["B"]).write_text('{"value": [1]}')
    old_c = _canonical(tmp_path, "C", "2026-01-01T00:00:00.000-03:00")
    old_c.with_name(old_c.name + ".manifest.json").write_text("{}")

    api = FakeOData({})
    out_dir = tmp_path / "series"
    rep = backfill.rebuild_state(
        series, out_dir, lambda code: _canonical(tmp_path, code, stamps[code])
    )
    assert api.calls == []
    assert sorted(rep.found) == ["A", "B"]
    assert sorted(rep.missing) == ["C", "D"]
    assert rep.undated == ["SEM_DATA"]
    assert backfill.load_state(out_dir / backfill.STATE_NAME) == {
        "A": stamps["A"],
        "B": stamps["B"],
    }


def test_resume_com_estado_completo_nao_baixa_nada(tmp_path: Path) -> None:
    stamps = {f"S{i}": f"2026-10-{i + 1:02d}T00:00:00.000-03:00" for i in range(5)}
    series = [_meta(c, s) for c, s in stamps.items()]
    for code, stamp in stamps.items():
        p = _canonical(tmp_path, code, stamp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.with_name(p.name + ".manifest.json").write_text("{}")
    out_dir = tmp_path / "series"
    path_for = lambda code: _canonical(tmp_path, code, stamps[code])  # noqa: E731
    backfill.rebuild_state(series, out_dir, path_for)

    api = FakeOData({})
    rep = backfill.run_backfill(series, api, out_dir, today=TODAY, path_for=path_for)
    assert api.calls == []
    assert sorted(rep.unchanged) == sorted(stamps) and not rep.downloaded


def test_cli_rebuild_state_nao_baixa(monkeypatch, tmp_path: Path) -> None:
    stamp = "2026-10-01T12:00:00.000-03:00"
    monkeypatch.setattr(
        catalog, "_fetch_all_series", lambda: [_meta("A", stamp), _meta("B", stamp)]
    )

    def no_download(self, url, dest, **kw):  # pragma: no cover - não pode rodar
        raise AssertionError("o --rebuild-state não pode baixar")

    monkeypatch.setattr(IpeadataClient, "download_resource", no_download)
    a = _canonical(tmp_path, "A", stamp)
    a.parent.mkdir(parents=True, exist_ok=True)
    a.with_name(a.name + ".manifest.json").write_text("{}")
    result = CliRunner().invoke(
        app, ["backfill", "--rebuild-state", "-o", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "1 série(s) com arquivo" in result.output
    state = json.loads((tmp_path / "series" / backfill.STATE_NAME).read_text())
    assert state == {"A": stamp}
