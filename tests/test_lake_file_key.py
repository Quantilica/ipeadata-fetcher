"""``file_key`` do core substitui o corte manual do ``@`` no nome dos brutos."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("quantilica.analytics.lake")

from quantilica.core.lake import file_key  # noqa: E402


@pytest.mark.parametrize(
    "nome",
    [
        "BM12_TJOVER12@20261101.json",
        "metadados@20261101T101500.json",
        "temas@20261101.json",
        "PRECOS_IPCA.json",
        "ABC.D_1@20261101.json",
    ],
)
def test_file_key_equivale_ao_corte_manual(nome: str) -> None:
    path = Path("/raw/ipeadata") / nome
    assert file_key(path) == path.stem.split("@")[0]
