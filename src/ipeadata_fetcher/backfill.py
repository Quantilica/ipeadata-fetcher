"""Carga histórica do Ipeadata: incremental por ``SERATUALIZACAO`` e em paralelo.

O OData de metadados traz, por série, ``SERATUALIZACAO`` (data da última
atualização). O estado (``SERCODIGO -> SERATUALIZACAO`` da última carga válida) fica
num sidecar JSON na pasta de saída; só se rebaixa a série cuja data mudou. Série
sem data conhecida é sempre rebaixada. Série vazia (``value: []``) é erro contado:
o arquivo vazio é descartado e a série não entra no estado.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .constants import valores_serie_url

STATE_NAME = "_seratualizacao.json"
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


def save_state(path: Path, state: dict[str, str]) -> None:
    """Grava o estado de forma atômica (arquivo temporário + rename)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), "utf-8")
    os.replace(tmp, path)


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
) -> BackfillReport:
    """Baixa as séries (``SERCODIGO``/``SERATUALIZACAO``) com um pool limitado.

    Args:
        series: Metadados das séries (dicts do OData).
        client: Cliente com ``download_resource(url, dest)``; o limite por host
            (``HostPolicy``) é do ``HttpClient`` dele.
        out_dir: Pasta de saída dos ``<SERCODIGO>@<today>.json``.
        today: Carimbo ``AAAAMMDD`` dos arquivos.
        workers: Downloads simultâneos (mínimo 1).
        resume: Pula séries cuja ``SERATUALIZACAO`` não mudou; ``False`` rebaixa tudo.
        progress: Recebe uma linha por série (opcional).
        save_every: Salva o estado a cada N séries concluídas.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / STATE_NAME
    state = load_state(state_path) if resume else {}
    report = BackfillReport()
    say = progress or (lambda _msg: None)

    todo: list[tuple[str, str]] = []
    for s in series:
        code = str(s["SERCODIGO"])
        stamp = str(s.get("SERATUALIZACAO") or "")
        if resume and stamp and state.get(code) == stamp:
            report.unchanged.append(code)
            continue
        todo.append((code, stamp))

    def fetch(code: str) -> str | None:
        dest = out_dir / f"{code}@{today}.json"
        client.download_resource(valores_serie_url(code), dest)
        problem = _check_payload(dest)
        if problem is not None:
            _discard(dest)
        return problem

    total = len(todo)
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch, code): (code, stamp) for code, stamp in todo}
        try:
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
                    save_state(state_path, state)
        finally:
            save_state(state_path, state)
    return report
