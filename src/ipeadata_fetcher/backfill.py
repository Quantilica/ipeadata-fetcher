"""Carga histórica do Ipeadata: incremental por ``SERATUALIZACAO`` e em paralelo.

O OData de metadados traz, por série, ``SERATUALIZACAO`` (data da última
atualização). O estado (``SERCODIGO -> SERATUALIZACAO`` da última carga válida) fica
num sidecar JSON na pasta de saída; só se rebaixa a série cuja data mudou. Série
sem data conhecida é sempre rebaixada. Série vazia (``value: []``) é erro contado:
o arquivo vazio é descartado e a série não entra no estado.

Uma carga segura o lock exclusivo ``<estado>.lock`` (``fcntl.flock``) do começo
ao fim: uma segunda carga na mesma pasta aborta com :class:`StateLockedError`.
``save_state`` ainda une o estado em memória ao que está em disco (vence a data
mais recente), então nenhum gravador apaga chaves de outro.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import datetime as dt
import fcntl
import json
import os
import threading
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .constants import valores_serie_url

STATE_NAME = "_seratualizacao.json"
LOCK_SUFFIX = ".lock"  # lock da carga inteira
_SAVE_LOCK_SUFFIX = ".save.lock"  # lock curto de cada gravação
DEFAULT_WORKERS = 3  # o que a carga regional de 11 GB (T0.11) usou sem falhas


class _Downloader(Protocol):
    def download_resource(self, url: str, dest: Path, *args: Any, **kw: Any) -> Any: ...


@dataclass
class BackfillReport:
    """Resultado de uma carga: contadores e séries com problema."""

    downloaded: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    state_save_errors: list[str] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return len(self.empty) + len(self.failed)


def load_state(path: Path) -> dict[str, str]:
    """Estado salvo; ausente ou corrompido vale como vazio (rebaixa tudo)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v}


def _stamp_key(stamp: str) -> tuple[int, Any]:
    """Chave de ordenação de ``SERATUALIZACAO``: data ISO se der, senão texto."""
    try:
        parsed = dt.datetime.fromisoformat(stamp)
    except ValueError:
        return (0, stamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return (1, parsed.timestamp())


def merge_states(base: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """União por código; no conflito vence a ``SERATUALIZACAO`` mais recente."""
    merged = dict(base)
    for code, stamp in new.items():
        old = merged.get(code)
        if old is None or _stamp_key(stamp) >= _stamp_key(old):
            merged[code] = stamp
    return merged


@contextlib.contextmanager
def _flock(path: Path, *, blocking: bool) -> Iterator[None]:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def save_state(path: Path, state: dict[str, str]) -> dict[str, str]:
    """Grava o estado unido ao que está em disco, de forma atômica.

    Lê o arquivo atual, une com ``state`` (:func:`merge_states`) e troca o
    arquivo por rename, tudo sob um lock curto: dois gravadores simultâneos
    não perdem chaves um do outro. Devolve o estado gravado.
    """
    with _flock(path.with_name(path.name + _SAVE_LOCK_SUFFIX), blocking=True):
        merged = merge_states(load_state(path), state)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(
                json.dumps(merged, ensure_ascii=False, sort_keys=True), "utf-8"
            )
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    return merged


class StateLockedError(RuntimeError):
    """Outra carga já segura o lock do estado nesta pasta."""


@contextlib.contextmanager
def state_lock(state_path: Path) -> Iterator[Path]:
    """Lock exclusivo e não bloqueante da carga sobre ``state_path``.

    Raises:
        StateLockedError: se outra carga (outro processo ou thread) já o segura.
    """
    lock_path = state_path.with_name(state_path.name + LOCK_SUFFIX)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise StateLockedError(
                f"Outra carga do Ipeadata já está em andamento nesta pasta "
                f"(lock {lock_path}). Aguarde ela terminar: duas cargas no "
                f"mesmo estado perdem séries do {state_path.name}."
            ) from exc
        try:
            yield lock_path
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _discard(path: Path) -> None:
    for p in (path, path.with_name(path.name + ".manifest.json")):
        p.unlink(missing_ok=True)


def _check_payload(path: Path) -> str | None:
    """``None`` se o JSON tem valores; ``"empty"`` ou uma mensagem de erro."""
    if not path.is_file():
        return "arquivo não gerado"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"JSON inválido: {exc}"
    values = data.get("value") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return "resposta sem o campo 'value'"
    return "empty" if not values else None


def run_backfill(
    series: Sequence[dict[str, Any]],
    client: _Downloader,
    out_dir: Path,
    *,
    today: str,
    workers: int = DEFAULT_WORKERS,
    resume: bool = True,
    progress: Callable[[str], None] | None = None,
    save_every: int = 50,
    path_for: Callable[[str], Path] | None = None,
) -> BackfillReport:
    """Baixa as séries (``SERCODIGO``/``SERATUALIZACAO``) com um pool limitado.

    Args:
        series: Metadados das séries (dicts do OData).
        client: Cliente com ``download_resource(url, dest)``; o limite por host
            (``HostPolicy``) é do ``HttpClient`` dele.
        out_dir: Pasta do estado ``_seratualizacao.json`` (e destino padrão).
        today: Carimbo ``AAAAMMDD`` dos arquivos (usado sem ``path_for``).
        workers: Downloads simultâneos (mínimo 1).
        resume: Pula séries cuja ``SERATUALIZACAO`` não mudou; ``False`` rebaixa tudo.
        progress: Recebe uma linha por série (opcional).
        save_every: Salva o estado a cada N séries concluídas.
        path_for: Destino canônico por código (mesmo ``path_builder`` do ``sync``);
            sem ele, usa ``out_dir/<SERCODIGO>@<today>.json``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / STATE_NAME
    with state_lock(state_path):
        return _run_locked(
            series,
            client,
            out_dir,
            state_path,
            today=today,
            workers=workers,
            resume=resume,
            say=progress or (lambda _msg: None),
            save_every=save_every,
            path_for=path_for,
        )


def _run_locked(
    series: Sequence[dict[str, Any]],
    client: _Downloader,
    out_dir: Path,
    state_path: Path,
    *,
    today: str,
    workers: int,
    resume: bool,
    say: Callable[[str], None],
    save_every: int,
    path_for: Callable[[str], Path] | None,
) -> BackfillReport:
    state = load_state(state_path) if resume else {}
    report = BackfillReport()

    todo: list[tuple[str, str]] = []
    for s in series:
        code = str(s["SERCODIGO"])
        stamp = str(s.get("SERATUALIZACAO") or "")
        if resume and stamp and state.get(code) == stamp:
            report.unchanged.append(code)
            continue
        todo.append((code, stamp))

    def fetch(code: str) -> str | None:
        dest = (
            path_for(code) if path_for is not None else out_dir / f"{code}@{today}.json"
        )
        client.download_resource(valores_serie_url(code), dest)
        problem = _check_payload(dest)
        if problem is not None:
            _discard(dest)
        return problem

    def checkpoint() -> None:
        # Uma falha de disco num checkpoint não pode derrubar o laço: antes, a
        # exceção saía do ``for`` enquanto o ``with`` do pool esperava as
        # milhares de séries já enfileiradas, que eram baixadas sem que o
        # estado fosse gravado de novo. Avisa e tenta no próximo checkpoint.
        try:
            save_state(state_path, state)
        except OSError as exc:
            report.state_save_errors.append(f"{type(exc).__name__}: {exc}")
            say(f"AVISO: estado não gravado ({exc}); nova tentativa adiante")

    total = len(todo)
    done = 0
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        futures = {pool.submit(fetch, code): (code, stamp) for code, stamp in todo}
        for fut in concurrent.futures.as_completed(futures):
            code, stamp = futures[fut]
            done += 1
            try:
                problem = fut.result()
            except Exception as exc:  # noqa: BLE001 - uma série não derruba a carga
                report.failed[code] = f"{type(exc).__name__}: {exc}"
                say(f"[{done}/{total}] {code} - FALHA: {exc}")
            else:
                if problem == "empty":
                    report.empty.append(code)
                    say(f"[{done}/{total}] {code} - VAZIA (erro contado)")
                elif problem is not None:
                    report.failed[code] = problem
                    say(f"[{done}/{total}] {code} - FALHA: {problem}")
                else:
                    report.downloaded.append(code)
                    if stamp:
                        state[code] = stamp
                    say(f"[{done}/{total}] {code} - ok")
            if done % save_every == 0:
                checkpoint()
    except BaseException:
        # Interrupção (Ctrl+C, erro inesperado): não baixa o que falta.
        pool.shutdown(wait=True, cancel_futures=True)
        with contextlib.suppress(OSError):
            save_state(state_path, state)
        raise
    pool.shutdown(wait=True)
    # A gravação final não engole erro: sem ela a próxima carga rebaixaria tudo.
    save_state(state_path, state)
    return report


@dataclass
class RebuildReport:
    """Resultado de :func:`rebuild_state`."""

    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    undated: list[str] = field(default_factory=list)
    state_size: int = 0


def rebuild_state(
    series: Sequence[dict[str, Any]],
    out_dir: Path,
    path_for: Callable[[str], Path],
) -> RebuildReport:
    """Reconstrói o estado a partir dos arquivos já baixados, sem rede.

    Para cada série com ``SERATUALIZACAO``, calcula o caminho canônico
    (``path_for``, o mesmo ``path_builder`` do ``sync``, com o carimbo da
    própria ``SERATUALIZACAO``). Se o arquivo ou o sidecar ``.manifest.json``
    existir (o ingest apaga o dado e mantém o sidecar), a versão atual já foi
    baixada: grava ``estado[SERCODIGO] = SERATUALIZACAO`` exato. Segura o mesmo
    lock da carga.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / STATE_NAME
    report = RebuildReport()
    found: dict[str, str] = {}
    for s in series:
        if "SERCODIGO" not in s:
            continue
        code = str(s["SERCODIGO"])
        stamp = str(s.get("SERATUALIZACAO") or "")
        if not stamp:
            report.undated.append(code)
            continue
        dest = path_for(code)
        sidecar = dest.with_name(dest.name + ".manifest.json")
        if dest.exists() or sidecar.exists():
            found[code] = stamp
            report.found.append(code)
        else:
            report.missing.append(code)
    with state_lock(state_path):
        report.state_size = len(save_state(state_path, found))
    return report
