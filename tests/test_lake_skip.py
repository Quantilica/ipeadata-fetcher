"""O build sem mudança decide por sidecars e rodapés, sem ler o JSON do bruto."""

from __future__ import annotations

import builtins
import hashlib
import io
import json
from pathlib import Path

import pytest

pytest.importorskip("quantilica.analytics.lake")

import polars as pl  # noqa: E402
import quantilica.analytics.lake as analytics_lake  # noqa: E402
import quantilica.core.manifests as manifests  # noqa: E402
from quantilica.analytics.lake import GroupMember, LakeWriter, check_dataset  # noqa: E402

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


@pytest.fixture
def sem_abrir_bruto(monkeypatch: pytest.MonkeyPatch, raw: Path):  # noqa: ANN201
    """Devolve ``armar()``: depois dela, nenhum ``open`` de JSON do bruto.

    Vigia ``builtins.open``, ``io.open`` e ``Path.open``. Só sidecars e a série
    vazia (que não deixa registro no lake) podem ser abertos.
    """
    raiz = str(raw.resolve())

    def vigia(original):  # noqa: ANN001, ANN202
        def aberto(file, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            caminho = str(file) if isinstance(file, str | Path) else ""
            if (
                caminho.startswith(raiz)
                and not caminho.endswith(".manifest.json")
                and not caminho.endswith(VAZIA)
            ):
                raise AssertionError(f"bruto aberto: {caminho}")
            return original(file, *args, **kwargs)

        return aberto

    def armar() -> None:
        monkeypatch.setattr(builtins, "open", vigia(builtins.open))
        monkeypatch.setattr(io, "open", vigia(io.open))
        original_path_open = Path.open

        def path_open(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
            return vigia(lambda f, *a, **k: original_path_open(Path(f), *a, **k))(
                self, *args, **kwargs
            )

        monkeypatch.setattr(Path, "open", path_open)

    return armar


def test_segunda_rodada_nao_abre_json_nem_le_para_somar(
    raw: Path, tmp_path: Path, sem_abrir_bruto, sem_hash_por_leitura: None
) -> None:
    lake = tmp_path / "lake"
    assert not converter.convert(raw, lake).errors
    sem_abrir_bruto()
    for alvo in (["valores"], ["valores_regional"], ["series"], None):
        res = converter.convert(raw, lake, datasets=alvo)
        assert not res.errors and res.converted <= 1  # só a dimensão `series`


def _revisar_inpc(raw: Path) -> None:
    """Revisão que acrescenta o ano 2022 à série (grupo novo, ano=2022)."""
    novo = raw / "series" / "PRECOS_INPC@20261110.json"
    _write(novo, {"value": _mensal("PRECOS_INPC", range(2020, 2023), 70.0)})
    _sidecar(novo)


def _membros_do_grupo(arquivo: Path) -> set[str]:
    return set(pl.read_parquet(arquivo, hive_partitioning=False)["_origem"].unique())


def test_conversao_interrompida_num_grupo_e_completada_na_rodada_seguinte(
    raw: Path, tmp_path: Path, leituras: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    _revisar_inpc(raw)
    grupo = (
        lake
        / "ipeadata"
        / "valores"
        / "base=macro"
        / "periodicidade=mensal"
        / "ano=2022"
        / "valores_macro_mensal.parquet"
    )
    assert "PRECOS_INPC" not in _membros_do_grupo(grupo)

    original = LakeWriter.write_group

    def cai_no_ano_2022(self, group_key, members, *, partitions=None, **kw):  # noqa: ANN001, ANN002, ANN003, ANN202
        if partitions and partitions.get("ano") == 2022:
            raise RuntimeError("sem espaço em disco")
        return original(self, group_key, members, partitions=partitions, **kw)

    with monkeypatch.context() as m:
        m.setattr(LakeWriter, "write_group", cai_no_ano_2022)
        interrompida = converter.convert(raw, lake, datasets=["valores"])
    assert any("valores_macro_mensal" in e for e in interrompida.errors)
    assert "PRECOS_INPC" not in _membros_do_grupo(grupo)  # o ano novo ficou de fora

    # os anos que gravaram já citam a série revisada: sem a declaração dos grupos
    # que ela ocupa, o caminho rápido daria a série por em dia e o ano 2022 nunca viria
    leituras.clear()
    res = converter.convert(raw, lake, datasets=["valores"])
    assert not res.errors and res.converted == 1
    assert "PRECOS_INPC@20261110.json" in leituras
    assert _membros_do_grupo(grupo) >= {"PRECOS_INPC", "PRECOS_IPCAG"}
    assert check_dataset(lake / "ipeadata" / "valores") == []

    leituras.clear()
    de_novo = converter.convert(raw, lake, datasets=["valores"])
    assert not de_novo.errors and de_novo.converted == 0
    assert leituras == [VAZIA]


def test_falha_em_outro_grupo_nao_esconde_o_grupo_que_falhou_entre_rodadas(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rodada seguinte à que falhou conta a série como convertida, não pulada."""
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    _revisar_inpc(raw)
    original = LakeWriter.write_group

    def cai_no_ano_2022(self, group_key, members, *, partitions=None, **kw):  # noqa: ANN001, ANN002, ANN003, ANN202
        if partitions and partitions.get("ano") == 2022:
            raise RuntimeError("kill")
        return original(self, group_key, members, partitions=partitions, **kw)

    with monkeypatch.context() as m:
        m.setattr(LakeWriter, "write_group", cai_no_ano_2022)
        converter.convert(raw, lake, datasets=["valores"])
    w = LakeWriter(lake / "ipeadata" / "valores", _descritor("valores"), force=False)
    raw_inpc = raw / "series" / "PRECOS_INPC@20261110.json"
    assert not w.origin_complete(
        raw_inpc,
        contract_version=lake_mod.CONTRACT_VERSION,
        converter_version=lake_mod.CONVERTER_VERSION,
    )
    assert len(w.origin_outputs(raw_inpc) or []) == 3  # 2020, 2021 e 2022


def _descritor(dataset: str):  # noqa: ANN202
    from quantilica.core.lake import DatasetDescriptor, partition_types_for

    chaves = lake_mod.VALORES_KEYS[dataset]
    return DatasetDescriptor(
        source_id="ipeadata",
        dataset_id=dataset,
        alias=dataset,
        partition_keys=chaves,
        partition_types=partition_types_for(chaves),
    )


def test_lake_gravado_sem_declaracao_reconverte_uma_vez_e_depois_pula(
    raw: Path, tmp_path: Path, leituras: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    with monkeypatch.context() as m:  # o lake como as versões anteriores o gravavam
        m.setattr(
            lake_mod,
            "GroupMember",
            lambda *a, **k: GroupMember(*a, **{**k, "origin_outputs": None}),
        )
        assert not converter.convert(raw, lake).errors

    leituras.clear()
    uma_vez = converter.convert(raw, lake, datasets=["valores"])
    assert not uma_vez.errors and uma_vez.converted == 6  # as 6 séries de `valores`
    assert len(leituras) > 1

    leituras.clear()
    depois = converter.convert(raw, lake, datasets=["valores"])
    assert not depois.errors and depois.converted == 0
    assert leituras == [VAZIA]
    assert check_dataset(lake / "ipeadata" / "valores") == []


def test_serie_que_sai_da_pasta_regional_muda_de_dataset(
    raw: Path, tmp_path: Path
) -> None:
    lake = tmp_path / "lake"
    codigo = "REG_X"
    linhas = [_row(codigo, f"{a}-01-01", float(a)) for a in (2000, 2001)]
    regional = raw / "regional" / f"{codigo}@20261105.json"
    _write(regional, {"value": linhas})
    _sidecar(regional)
    assert not converter.convert(raw, lake).errors
    assert list((lake / "ipeadata" / "valores_regional").rglob("*.parquet"))

    # os mesmos bytes, o mesmo nome, noutra pasta: o sha256 não muda, o destino sim
    macro = raw / "macro" / regional.name
    macro.write_bytes(regional.read_bytes())
    _sidecar(macro)
    regional.unlink()
    regional.with_name(regional.name + ".manifest.json").unlink()

    res = converter.convert(raw, lake)

    assert not res.errors and res.converted >= 1
    em_valores = _membros_de_dataset(lake / "ipeadata" / "valores")
    assert codigo in em_valores
    assert codigo not in _membros_de_dataset(lake / "ipeadata" / "valores_regional")


def test_serie_que_sai_da_pasta_regional_para_social_muda_de_dataset(
    raw: Path, tmp_path: Path
) -> None:
    lake = tmp_path / "lake"
    codigo = "REG_X"
    linhas = [_row(codigo, f"{a}-01-01", float(a)) for a in (2000, 2001)]
    regional = raw / "regional" / f"{codigo}@20261105.json"
    _write(regional, {"value": linhas})
    _sidecar(regional)
    assert not converter.convert(raw, lake).errors
    assert list((lake / "ipeadata" / "valores_regional").rglob("*.parquet"))

    # os mesmos bytes (sem NIVNOME) noutra pasta: o sha256 não muda, o destino sim
    social = raw / "social" / regional.name
    social.write_bytes(regional.read_bytes())
    _sidecar(social)
    regional.unlink()
    regional.with_name(regional.name + ".manifest.json").unlink()

    res = converter.convert(raw, lake)

    assert not res.errors and res.converted >= 1
    em_valores = _membros_de_dataset(lake / "ipeadata" / "valores")
    assert codigo in em_valores
    assert codigo not in _membros_de_dataset(lake / "ipeadata" / "valores_regional")


def _membros_de_dataset(diretorio: Path) -> set[str]:
    achados: set[str] = set()
    for arquivo in diretorio.rglob("*.parquet"):
        achados |= _membros_do_grupo(arquivo)
    return achados


def test_hash_que_falha_com_oserror_cai_no_caminho_completo(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)

    def falha(original):  # noqa: ANN001, ANN202
        def sha(path):  # noqa: ANN001, ANN202
            if Path(path).name.startswith("PRECOS_INPC@"):
                raise OSError(5, "Input/output error")
            return original(path)

        return sha

    monkeypatch.setattr(lake_mod, "sha256_file", falha(lake_mod.sha256_file))
    monkeypatch.setattr(
        analytics_lake, "sha256_file", falha(analytics_lake.sha256_file)
    )

    res = converter.convert(raw, lake, datasets=["valores"])  # não levanta

    assert any("PRECOS_INPC" in e for e in res.errors)
    assert res.converted == 0


def test_dimensao_com_sha256_que_falha_nao_derruba_o_convert(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake, datasets=["series"])
    original = analytics_lake.sha256_file

    def sha(path):  # noqa: ANN001, ANN202
        if Path(path).name.startswith("metadados@"):
            raise OSError(5, "Input/output error")
        return original(path)

    monkeypatch.setattr(analytics_lake, "sha256_file", sha)

    res = converter.convert(raw, lake, datasets=["series"])  # não levanta

    assert res.errors  # o erro de escrita, reportado
