"""O build sem mudança decide por sidecars e rodapés, sem ler o JSON do bruto."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("quantilica.analytics.lake")

import quantilica.core.manifests as manifests  # noqa: E402
from quantilica.analytics.lake import check_dataset  # noqa: E402

import ipeadata_fetcher.lake as lake_mod  # noqa: E402
from ipeadata_fetcher.lake import converter  # noqa: E402

from .lake_fixtures import META, _mensal, _row, _write, build_raw  # noqa: E402

N_SERIES = 9  # séries com valores nas fixtures
VAZIA = "VAZIA@20261105.json"


def _sidecar(arquivo: Path) -> None:
    """Sidecar de manifesto como o do fetcher: o sha256 sem reler o arquivo."""
    dados = arquivo.read_bytes()
    alvo = arquivo.with_name(arquivo.name + ".manifest.json")
    alvo.write_text(
        json.dumps(
            {"sha256": hashlib.sha256(dados).hexdigest(), "size_bytes": len(dados)}
        ),
        encoding="utf-8",
    )


def _sidecars(raw: Path) -> None:
    for f in raw.rglob("*.json"):
        if not f.name.endswith(".manifest.json"):
            _sidecar(f)


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    build_raw(tmp_path / "raw")
    _sidecars(tmp_path / "raw")
    return tmp_path / "raw"


@pytest.fixture
def leituras(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Todo JSON do bruto aberto para leitura (de dados ou de metadados)."""
    abertos: list[str] = []
    original = lake_mod._read_json_items

    def espia(file_path: Path):  # noqa: ANN202
        abertos.append(Path(file_path).name)
        return original(file_path)

    monkeypatch.setattr(lake_mod, "_read_json_items", espia)
    return abertos


@pytest.fixture
def sem_hash_por_leitura(monkeypatch: pytest.MonkeyPatch) -> None:
    """O sha256 tem de vir do sidecar: ler o arquivo para somar é falha."""

    def falha(path):  # noqa: ANN001, ANN202
        raise AssertionError(f"bruto lido para o sha256: {path}")

    monkeypatch.setattr(manifests, "sha256_file", falha)


def _resultado(res) -> tuple[int, int, list[str]]:  # noqa: ANN001
    return res.converted, res.skipped, res.errors


@pytest.mark.parametrize("dataset", ["valores", "valores_regional"])
def test_segunda_rodada_de_um_dataset_nao_le_series_nem_metadados(
    raw: Path,
    tmp_path: Path,
    leituras: list[str],
    sem_hash_por_leitura: None,
    dataset: str,
) -> None:
    lake = tmp_path / "lake"
    assert not converter.convert(raw, lake).errors  # todos os datasets

    leituras.clear()
    res = converter.convert(raw, lake, datasets=[dataset])

    assert not res.errors
    assert res.converted == 0
    # só a série vazia, que não deixa registro no lake, tem de ser aberta
    assert leituras == [VAZIA]
    assert res.skipped >= 1


def test_segunda_rodada_conta_igual_ao_caminho_completo(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    for alvo in (["valores"], ["valores_regional"], None):
        rapido = _resultado(converter.convert(raw, lake, datasets=alvo))
        with monkeypatch.context() as m:
            m.setattr(lake_mod, "_pular_sem_ler_bruto", lambda *a, **k: None)
            completo = _resultado(converter.convert(raw, lake, datasets=alvo))
        # o caminho completo conta a dimensão `series` como convertida; o resto bate
        if alvo is None:
            assert rapido == completo
        else:
            assert rapido[1:] == completo[1:]
            assert rapido[0] == 0


def test_dimensoes_em_dia_nao_sao_lidas(
    raw: Path, tmp_path: Path, leituras: list[str], sem_hash_por_leitura: None
) -> None:
    lake = tmp_path / "lake"
    primeira = converter.convert(raw, lake, datasets=["series"])
    assert not primeira.errors and leituras == ["metadados@20261101.json"]

    leituras.clear()
    res = converter.convert(raw, lake, datasets=["series"])
    assert _resultado(res) == _resultado(primeira)  # a dimensão segue contada
    assert leituras == []


def test_serie_revisada_so_ela_e_relida_e_convertida(
    raw: Path, tmp_path: Path, leituras: list[str]
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    novo = raw / "series" / "PRECOS_INPC@20261110.json"
    _write(novo, {"value": _mensal("PRECOS_INPC", range(2020, 2022), 70.0)})
    _sidecar(novo)

    leituras.clear()
    res = converter.convert(raw, lake, datasets=["valores"])

    assert not res.errors and res.converted == 1
    assert "PRECOS_INPC@20261110.json" in leituras
    assert check_dataset(lake / "ipeadata" / "valores") == []


def test_serie_nova_converte(raw: Path, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    nova = raw / "macro" / "NOVA_X@20261110.json"
    _write(
        nova,
        {
            "value": [
                {
                    "SERCODIGO": "NOVA_X",
                    "VALDATA": "2022-01-01T00:00:00-03:00",
                    "VALVALOR": 1.0,
                    "NIVNOME": "",
                    "TERCODIGO": "",
                }
            ]
        },
    )
    _sidecar(nova)

    res = converter.convert(raw, lake, datasets=["valores"])

    assert not res.errors and res.converted == 1


def test_force_reconverte_tudo(raw: Path, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    res = converter.convert(raw, lake, datasets=["valores"], force=True)
    assert not res.errors
    assert res.converted == 6 and res.skipped == 1  # as 6 séries de `valores`


def test_metadados_novos_mudam_a_periodicidade_sem_o_dataset_series(
    raw: Path, tmp_path: Path
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    novo = {
        "value": [
            {**item, "PERNOME": "Mensal"} if item["SERCODIGO"] == "PIB_ANUAL" else item
            for item in META["value"]
        ]
    }
    arq = raw / "dimensoes" / "metadados@20261110.json"
    _write(arq, novo)
    _sidecar(arq)

    # só `valores`: a dimensão `series` do lake continua a antiga e não serve de fonte
    res = converter.convert(raw, lake, datasets=["valores"])

    assert not res.errors
    base = lake / "ipeadata" / "valores" / "base=macro"
    assert list((base / "periodicidade=mensal").rglob("ano=1950/*.parquet"))
    assert not list((base / "periodicidade=anual").rglob("ano=1950/*.parquet"))


def test_visao_parcial_do_bruto_segue_avisando_sem_ler_as_series(
    tmp_path: Path, leituras: list[str]
) -> None:
    raw, lake = tmp_path / "raw", tmp_path / "lake"
    codigos = [f"MUITAS_{i:03d}" for i in range(40)]
    _write(
        raw / "dimensoes" / "metadados@20261101.json",
        {"value": [{"SERCODIGO": c, "PERNOME": "Anual"} for c in codigos]},
    )
    for c in codigos:
        _write(
            raw / "macro" / f"{c}@20261105.json",
            {"value": [_row(c, f"{a}-01-01", float(a)) for a in (2020, 2021)]},
        )
    _sidecars(raw)
    assert not converter.convert(raw, lake).errors
    for c in codigos[:30]:  # 30 > max(25, 2%) saem do bruto
        (raw / "macro" / f"{c}@20261105.json").unlink()

    leituras.clear()
    res = converter.convert(raw, lake, datasets=["valores"])

    assert res.converted == 0 and res.skipped == 10
    assert len(res.errors) == 1 and "visão parcial" in res.errors[0]
    assert leituras == []
    assert len(list((lake / "ipeadata" / "valores").rglob("*.parquet"))) == 2
