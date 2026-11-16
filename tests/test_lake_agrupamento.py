"""Agrupamento por ano dos valores: segunda execução, revisões, migração e auditoria."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("quantilica.analytics.lake")

import polars as pl  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from quantilica.analytics import lake_audit  # noqa: E402
from quantilica.analytics.lake import (  # noqa: E402
    META_MEMBERS,
    LakeWriter,
    check_dataset,
    scan_dataset,
)
from quantilica.core.lake import (  # noqa: E402
    DatasetDescriptor,
    file_key,
    partition_types_for,
)

import ipeadata_fetcher.lake as lake_mod  # noqa: E402
from ipeadata_fetcher.lake import converter  # noqa: E402

from .lake_fixtures import (  # noqa: E402
    GOLDEN,
    META,
    _mensal,
    _row,
    _write,
    build_raw,
    snapshot,
)

N_SERIES = 9  # séries com valores nas fixtures (a vazia não conta)
DIM = 1  # a dimensão `series` (metadados) sempre conta como convertida


def _legacy_valores(raw_files, writers, periodicidades, pastas_da_serie, res) -> None:
    """O conversor anterior: um Parquet por série (e nível) por periodicidade."""
    chaves = {
        "valores": ["base", "periodicidade"],
        "valores_regional": ["nivel", "periodicidade"],
    }
    for raw in raw_files:
        pastas = pastas_da_serie.get(file_key(raw), set())
        prepared = lake_mod._prepare_series(raw, pastas, periodicidades, quiet=True)
        if prepared is None:
            res.skipped += 1
            continue
        keys = chaves[prepared.dataset]
        writer = LakeWriter(
            writers[prepared.dataset].dataset_dir,
            DatasetDescriptor(
                source_id="ipeadata",
                dataset_id=prepared.dataset,
                alias=prepared.dataset,
                partition_keys=keys,
                partition_types=partition_types_for(keys),
            ),
        )
        df = prepared.df.drop("ano")
        per = prepared.periodicidade
        if prepared.dataset == "valores_regional":
            for nivel in df["nivel"].unique(maintain_order=True).to_list():
                part = df.filter(pl.col("nivel") == nivel)
                writer.write_polars(
                    part, src=raw, partitions={"nivel": nivel, "periodicidade": per}
                )
        else:
            writer.write_polars(
                df,
                src=raw,
                partitions={"base": df["base"][0], "periodicidade": per},
            )
        res.converted += 1


def _legacy_convert(raw: Path, lake: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as m:
        m.setattr(lake_mod, "_convert_valores", _legacy_valores)
        res = converter.convert(raw, lake)
    assert not res.errors


def _dataset(lake: Path, nome: str = "valores") -> Path:
    return lake / "ipeadata" / nome


def _parquets(lake: Path, nome: str = "valores") -> list[Path]:
    return sorted(_dataset(lake, nome).rglob("*.parquet"))


def _estado(lake: Path) -> dict[Path, tuple[int, int]]:
    return {
        p: (p.stat().st_mtime_ns, p.stat().st_ino)
        for nome in ("valores", "valores_regional")
        for p in _parquets(lake, nome)
    }


def _membros(path: Path) -> dict:
    return json.loads(pq.ParquetFile(path).metadata.metadata[META_MEMBERS.encode()])


def _linhas(lake: Path, nome: str = "valores") -> pl.DataFrame:
    return scan_dataset(_dataset(lake, nome)).collect()


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    build_raw(tmp_path / "raw")
    return tmp_path / "raw"


@pytest.fixture
def leituras(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Séries relidas para virar fatia (só as que têm de ser escritas)."""
    vistas: list[str] = []
    original = lake_mod._Slices.get

    def espiar(self, serie, destino):
        if serie.raw_file not in self._done:
            vistas.append(serie.key)
        return original(self, serie, destino)

    monkeypatch.setattr(lake_mod._Slices, "get", espiar)
    return vistas


def test_simulacao_do_conversor_antigo_bate_com_o_golden(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O auxiliar que recria o layout antigo é fiel: reproduz o golden commitado."""
    lake = tmp_path / "lake"
    _legacy_convert(raw, lake, monkeypatch)

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["lake"]
    obtido = json.loads(json.dumps(snapshot(lake), ensure_ascii=False))
    for dataset, particoes in golden.items():
        for particao, dados in particoes.items():
            esperado = {
                k: v for k, v in dados.items() if k != "tipos_de_valvalor_no_arquivo"
            }
            lido = {
                k: v
                for k, v in obtido[dataset][particao].items()
                if k != "tipos_de_valvalor_no_arquivo"
            }
            assert lido == esperado, (dataset, particao)
    assert not list(_dataset(lake).rglob("ano=*"))


def test_membros_no_rodape_e_origem_nas_linhas(raw: Path, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    res = converter.convert(raw, lake)
    assert not res.errors

    arquivo = _dataset(lake) / "base=macro/periodicidade=mensal/ano=2020"
    arquivo = arquivo / "valores_macro_mensal.parquet"
    membros = _membros(arquivo)
    # Uma série por membro, com a chave do arquivo bruto; 12 meses cada.
    assert sorted(membros) == ["PRECOS_ANO", "PRECOS_INPC", "PRECOS_IPCAG"]
    assert {m["rows"] for m in membros.values()} == {12, 3}
    assert all(
        m["origin_sha256"]
        and m["contract_version"] == 1
        and m["converter_version"] == "1"
        for m in membros.values()
    )
    colunas = pq.ParquetFile(arquivo).schema_arrow.names
    assert colunas == [
        *("sercodigo", "valdata", "valvalor", "nivnome", "tercodigo", "data", "valor"),
        "_origem",
    ]
    df = _linhas(lake).filter(
        pl.col("periodicidade") == "mensal", pl.col("ano") == 2020
    )
    assert df.group_by("_origem").len().sort("_origem").rows() == [
        ("PRECOS_ANO", 3),
        ("PRECOS_INPC", 12),
        ("PRECOS_IPCAG", 12),
    ]
    for nome in ("valores", "valores_regional"):
        assert check_dataset(_dataset(lake, nome)) == []


def test_segunda_execucao_nao_reescreve_arquivo_nem_gera_fatia(
    raw: Path, tmp_path: Path, leituras: list[str]
) -> None:
    lake = tmp_path / "lake"
    assert not converter.convert(raw, lake).errors
    assert len(leituras) == N_SERIES
    leituras.clear()
    antes = _estado(lake)

    res = converter.convert(raw, lake)

    assert not res.errors
    assert res.converted == DIM and res.skipped == N_SERIES + 1  # + a série vazia
    # Nada a escrever: nenhuma fatia foi gerada. Os JSON, porém, são todos lidos de
    # novo (é de onde se sabe os anos de cada série para montar a lista de membros).
    assert leituras == []
    assert _estado(lake) == antes  # nenhum arquivo reescrito
    assert not list((lake / "ipeadata").rglob(".tmp/*"))


def test_serie_revisada_reescreve_so_os_anos_dela(
    raw: Path, tmp_path: Path, leituras: list[str]
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    leituras.clear()
    antes = _estado(lake)

    # PRECOS_INPC é revisada: ganha valores novos em 2021 (mesmo conjunto de anos).
    novas = _mensal("PRECOS_INPC", range(2020, 2022), 70.0)
    _write(raw / "series" / "PRECOS_INPC@20261110.json", {"value": novas})
    res = converter.convert(raw, lake)

    assert not res.errors and res.converted == DIM + 1
    assert leituras == ["PRECOS_INPC"]
    depois = _estado(lake)
    mudou = {p.parent.name for p in depois if depois[p] != antes.get(p)}
    assert mudou == {"ano=2020", "ano=2021"}
    df = _linhas(lake).filter(pl.col("_origem") == "PRECOS_INPC")
    assert df.height == 24 and df["valor"].min() > 70


def test_serie_que_perde_um_ano_sai_do_grupo_dele(raw: Path, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    g2020 = _dataset(lake) / "base=macro/periodicidade=mensal/ano=2020"
    g2019 = _dataset(lake) / "base=macro/periodicidade=mensal/ano=2019"
    assert (g2019 / "valores_macro_mensal.parquet").exists()
    assert "PRECOS_IPCAG" in _membros(g2020 / "valores_macro_mensal.parquet")

    # PRECOS_IPCAG revisada: sem 2019 e sem 2020, com 2023.
    novas = _mensal("PRECOS_IPCAG", range(2021, 2024), 100.0)
    _write(raw / "macro" / "PRECOS_IPCAG@20261110.json", {"value": novas})
    res = converter.convert(raw, lake)

    assert not res.errors
    # 2020: o grupo continua com as outras séries, sem a IPCAG.
    assert sorted(_membros(g2020 / "valores_macro_mensal.parquet")) == [
        "PRECOS_ANO",
        "PRECOS_INPC",
    ]
    # 2019: só a IPCAG tinha linhas; o grupo e a pasta saem.
    assert not g2019.exists()
    # 2023: grupo novo.
    assert (
        _dataset(lake)
        / "base=macro/periodicidade=mensal/ano=2023/valores_macro_mensal.parquet"
    ).exists()
    df = _linhas(lake).filter(pl.col("_origem") == "PRECOS_IPCAG")
    assert df["ano"].unique().sort().to_list() == [2021, 2022, 2023]
    assert df.height == 36
    assert check_dataset(_dataset(lake)) == []


def test_serie_que_sai_do_bruto_sai_dos_grupos(raw: Path, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    for f in raw.glob("*/PRECOS_INPC@*.json"):
        f.unlink()

    res = converter.convert(raw, lake)

    assert not res.errors
    assert "PRECOS_INPC" not in set(_linhas(lake)["_origem"].to_list())
    g2020 = _dataset(lake) / "base=macro/periodicidade=mensal/ano=2020"
    assert sorted(_membros(g2020 / "valores_macro_mensal.parquet")) == [
        "PRECOS_ANO",
        "PRECOS_IPCAG",
    ]


def test_serie_que_muda_de_periodicidade_muda_de_pasta_sem_duplicar(
    raw: Path, tmp_path: Path
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    antes = _linhas(lake).filter(pl.col("_origem") == "PRECOS_ANO").height
    meta = json.loads(json.dumps(META))
    for item in meta["value"]:
        if item["SERCODIGO"] == "PRECOS_ANO":
            item["PERNOME"] = "Anual"
    _write(raw / "dimensoes" / "metadados@20261110.json", meta)

    res = converter.convert(raw, lake)

    assert not res.errors
    df = _linhas(lake).filter(pl.col("_origem") == "PRECOS_ANO")
    assert df.height == antes  # nenhuma linha duplicada
    assert df["periodicidade"].unique().to_list() == ["anual"]
    # A pasta mensal de 2021 ainda tem as outras séries; a de 2020 também.
    mensal = _linhas(lake).filter(pl.col("periodicidade") == "mensal")
    assert "PRECOS_ANO" not in set(mensal["_origem"].to_list())


def test_migracao_do_layout_antigo_sem_duplicar_linhas(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    _legacy_convert(raw, lake, monkeypatch)
    antigos = _parquets(lake) + _parquets(lake, "valores_regional")
    assert len(antigos) == 12
    linhas = {
        n: scan_dataset(_dataset(lake, n)).collect().height
        for n in ("valores", "valores_regional")
    }

    res = converter.convert(raw, lake)

    assert not res.errors
    assert res.converted == N_SERIES + DIM
    for nome, n in linhas.items():
        df = scan_dataset(_dataset(lake, nome)).collect()
        assert df.height == n, nome  # nenhuma linha duplicada
        assert check_dataset(_dataset(lake, nome)) == []
        # Nenhum Parquet antigo (direto na pasta da periodicidade) sobrou.
        assert not list(_dataset(lake, nome).glob("*/*/*.parquet")), nome
    # Idempotente: a passada seguinte não mexe em nada.
    antes = _estado(lake)
    assert converter.convert(raw, lake).converted == DIM
    assert _estado(lake) == antes
    # E o conteúdo é o do golden (migrado == convertido do zero).
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["lake"]
    obtido = json.loads(json.dumps(snapshot(lake), ensure_ascii=False))
    for dataset, particoes in golden.items():
        for particao, dados in particoes.items():
            a = {k: v for k, v in dados.items() if k != "tipos_de_valvalor_no_arquivo"}
            b = {
                k: v
                for k, v in obtido[dataset][particao].items()
                if k != "tipos_de_valvalor_no_arquivo"
            }
            assert a == b, (dataset, particao)


def test_migracao_nao_apaga_o_que_o_grupo_nao_cobre(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    _legacy_convert(raw, lake, monkeypatch)
    pasta = _dataset(lake) / "base=macro/periodicidade=mensal"
    # Parquet de uma série que não está mais no bruto: o grupo não tem as linhas dela.
    orfao = pasta / "SERIE_ANTIGA.parquet"
    shutil.copy2(pasta / "PRECOS_IPCAG.parquet", orfao)
    # Arquivo com o nome de uma série vigente que não é deste dataset (sem rodapé).
    alheio = pasta / "PRECOS_INPC.parquet"
    pq.write_table(pa.table({"x": [1]}), alheio)

    res = converter.convert(raw, lake)

    # Nada é apagado; o resíduo do layout antigo é listado como erro, com o caminho.
    assert len(res.errors) == 2
    assert any(str(orfao) in e for e in res.errors)
    assert any(str(alheio) in e for e in res.errors)
    assert orfao.exists() and alheio.exists()
    assert sorted(p.name for p in pasta.glob("*.parquet")) == [
        "PRECOS_INPC.parquet",
        "SERIE_ANTIGA.parquet",
    ]
    assert not (pasta / "PRECOS_IPCAG.parquet").exists()


def test_json_ilegivel_e_erro_e_nao_descarta_nada(raw: Path, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    antes = {
        p: pq.ParquetFile(p).metadata.num_rows
        for n in ("valores", "valores_regional")
        for p in _parquets(lake, n)
    }
    (raw / "macro" / "PRECOS_IPCAG@20261105.json").write_text("{quebrado")

    res = converter.convert(raw, lake)

    assert len(res.errors) == 1 and "PRECOS_IPCAG" in res.errors[0]
    depois = {
        p: pq.ParquetFile(p).metadata.num_rows
        for n in ("valores", "valores_regional")
        for p in _parquets(lake, n)
    }
    assert depois == antes  # a série quebrada continua onde estava


def test_linha_sem_data_e_erro_da_serie_e_nao_cria_quarentena_de_ano(
    raw: Path, tmp_path: Path
) -> None:
    lake = tmp_path / "lake"
    assert not converter.convert(raw, lake).errors
    antes = _linhas(lake).height
    linhas = [
        _row("PIB_ANUAL", "2020-01-01", 1.0),
        _row("PIB_ANUAL", "2021-01-01", 2.0),
    ]
    linhas[1]["VALDATA"] = "sem-data"
    _write(raw / "macro" / "PIB_ANUAL@20261110.json", {"value": linhas})

    res = converter.convert(raw, lake)

    assert len(res.errors) == 1
    assert "PIB_ANUAL" in res.errors[0] and "1 linha(s) sem data" in res.errors[0]
    assert not list(_dataset(lake).rglob("ano=__HIVE_DEFAULT_PARTITION__"))
    # A série não foi tocada: o lake continua com as linhas da versão anterior.
    assert _linhas(lake).height == antes
    assert len(_linhas(lake).filter(pl.col("_origem") == "PIB_ANUAL")) == 74
    from quantilica.core.lake_profile import profile_from_lake

    perfil = profile_from_lake(lake, "ipeadata", "valores").perfil
    assert perfil["granularidade"] == "anual"
    assert perfil["periodos"][0] == "1950"


def test_serie_nova_sem_data_valida_tambem_e_erro(raw: Path, tmp_path: Path) -> None:
    _write(
        raw / "macro" / "NOVA_X@20261110.json",
        {"value": [{**_row("NOVA_X", "2020-01-01", 1.0), "VALDATA": None}]},
    )
    res = converter.convert(raw, tmp_path / "lake")
    assert len(res.errors) == 1 and "NOVA_X" in res.errors[0]
    assert not list(_dataset(tmp_path / "lake").rglob("ano=__HIVE_DEFAULT_PARTITION__"))


def test_json_quebrado_de_outra_serie_nao_trava_o_prune_dos_demais(
    raw: Path, tmp_path: Path
) -> None:
    """PRECOS_ANO passa de mensal a anual com o JSON de CAMBIO_D quebrado: a primeira
    sai dos grupos mensais (sem linhas duplicadas) e CAMBIO_D não perde nada."""
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    antes = _linhas(lake)
    meta = json.loads(json.dumps(META))
    for item in meta["value"]:
        if item["SERCODIGO"] == "PRECOS_ANO":
            item["PERNOME"] = "Anual"
    _write(raw / "dimensoes" / "metadados@20261110.json", meta)
    (raw / "series" / "CAMBIO_D@20261105.json").write_text("{quebrado")

    res = converter.convert(raw, lake)

    assert len(res.errors) == 1 and "CAMBIO_D" in res.errors[0]
    df = _linhas(lake)
    ano = df.filter(pl.col("_origem") == "PRECOS_ANO")
    assert ano.height == antes.filter(pl.col("_origem") == "PRECOS_ANO").height
    assert ano["periodicidade"].unique().to_list() == ["anual"]  # sem cópia mensal
    cambio = df.filter(pl.col("_origem") == "CAMBIO_D")
    assert cambio.height == antes.filter(pl.col("_origem") == "CAMBIO_D").height == 6
    assert df.height == antes.height  # nenhuma linha duplicada nem perdida
    assert check_dataset(_dataset(lake)) == []


def test_prune_so_e_desligado_nos_grupos_da_serie_que_falhou(
    raw: Path, tmp_path: Path
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    # Sai do bruto uma série qualquer (PRECOS_INPC) e quebra outra (PIB_ANUAL, que só
    # está em grupos anuais): o grupo mensal de 2020 descarta a INPC, o anual não.
    for f in raw.glob("*/PRECOS_INPC@*.json"):
        f.unlink()
    (raw / "macro" / "PIB_ANUAL@20261105.json").write_text("{quebrado")

    res = converter.convert(raw, lake)

    assert len(res.errors) == 1 and "PIB_ANUAL" in res.errors[0]
    df = _linhas(lake)
    assert "PRECOS_INPC" not in set(df["_origem"].to_list())
    assert len(df.filter(pl.col("_origem") == "PIB_ANUAL")) == 74


def test_versao_vazia_de_serie_que_esta_no_lake_e_erro_e_nao_apaga(
    raw: Path, tmp_path: Path
) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    antes = _linhas(lake).height
    _write(raw / "macro" / "PIB_ANUAL@20261110.json", {"value": []})
    # e outra sem VALDATA/VALVALOR
    _write(
        raw / "macro" / "PRECOS_IPCAG@20261110.json",
        {"value": [{"SERCODIGO": "PRECOS_IPCAG", "OUTRA": 1}]},
    )

    res = converter.convert(raw, lake)

    assert len(res.errors) == 2
    assert {e.split("série ")[1].split("@")[0] for e in res.errors} == {
        "PIB_ANUAL",
        "PRECOS_IPCAG",
    }
    assert _linhas(lake).height == antes  # nada foi apagado


def test_versao_vazia_de_serie_so_com_parquet_antigo_nao_remove_o_antigo(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    _legacy_convert(raw, lake, monkeypatch)
    _write(raw / "macro" / "PRECOS_IPCAG@20261110.json", {"value": []})

    res = converter.convert(raw, lake)

    antigo = _dataset(lake) / "base=macro/periodicidade=mensal/PRECOS_IPCAG.parquet"
    assert antigo.exists()
    assert any("PRECOS_IPCAG" in e and "já está no lake" in e for e in res.errors)
    # as outras séries migraram e a antiga delas saiu
    assert not (antigo.parent / "PRECOS_INPC.parquet").exists()


def test_serie_vazia_que_nunca_esteve_no_lake_so_e_pulada(
    raw: Path, tmp_path: Path
) -> None:
    res = converter.convert(raw, tmp_path / "lake")  # VAZIA nunca teve linhas
    assert not res.errors and res.skipped == 1


def _muitas_series(raw: Path, n: int) -> list[str]:
    codigos = [f"MUITAS_{i:03d}" for i in range(n)]
    meta = {"value": [{"SERCODIGO": c, "PERNOME": "Anual"} for c in codigos]}
    _write(raw / "dimensoes" / "metadados@20261101.json", meta)
    for c in codigos:
        _write(
            raw / "macro" / f"{c}@20261105.json",
            {"value": [_row(c, f"{a}-01-01", float(a)) for a in (2020, 2021)]},
        )
    return codigos


def _bruto_com(tmp_path: Path, n: int) -> Path:
    raw = tmp_path / "raw"
    _muitas_series(raw, n)
    return raw


def test_visao_parcial_do_bruto_acima_do_limite_nao_apaga_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("IPEADATA_FETCHER_ALLOW_PRUNE", raising=False)
    raw = _bruto_com(tmp_path, 60)
    lake = tmp_path / "lake"
    assert not converter.convert(raw, lake).errors
    antes = _linhas(lake).height
    for i in range(26):  # 26 > max(25, 2% de 60)
        (raw / f"macro/MUITAS_{i:03d}@20261105.json").unlink()

    res = converter.convert(raw, lake)

    assert len(res.errors) == 1
    assert (
        "26 das 60 séries" in res.errors[0]
        and "IPEADATA_FETCHER_ALLOW_PRUNE=1" in res.errors[0]
    )
    assert _linhas(lake).height == antes  # nada foi descartado

    monkeypatch.setenv("IPEADATA_FETCHER_ALLOW_PRUNE", "1")
    res = converter.convert(raw, lake)
    assert not res.errors
    assert _linhas(lake).height == (60 - 26) * 2


def test_visao_parcial_no_limite_ainda_aplica_o_prune(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("IPEADATA_FETCHER_ALLOW_PRUNE", raising=False)
    raw = _bruto_com(tmp_path, 60)
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    for i in range(25):  # exatamente o limite: ainda vale
        (raw / f"macro/MUITAS_{i:03d}@20261105.json").unlink()

    res = converter.convert(raw, lake)

    assert not res.errors
    assert _linhas(lake).height == (60 - 25) * 2


def test_limite_de_visao_parcial_cresce_com_o_lake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com 2% maior que 25 (1.500 séries), o limite é a fração; aqui, ao contrário,
    com poucas séries qualquer perda é pequena: 3 de 10 não trava."""
    monkeypatch.delenv("IPEADATA_FETCHER_ALLOW_PRUNE", raising=False)
    raw = _bruto_com(tmp_path, 10)
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    for i in range(3):
        (raw / f"macro/MUITAS_{i:03d}@20261105.json").unlink()
    assert not converter.convert(raw, lake).errors
    assert _linhas(lake).height == 7 * 2


def test_auditoria_do_lake_agrupado(raw: Path, tmp_path: Path) -> None:
    # O lake_audit espera <fonte>/<pasta>/<arquivo> sob o diretório de entrada.
    entrada = tmp_path / "entrada"
    shutil.copytree(raw, entrada / "ipeadata")
    _tira_o_que_nao_gera_parquet(entrada)
    lake = tmp_path / "lake"
    assert not converter.convert(entrada / "ipeadata", lake).errors

    report = lake_audit(lake, input_dir=entrada, converters={}, rehash=True)

    assert report.ok, report.to_text()


def test_auditoria_do_lake_migrado(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entrada = tmp_path / "entrada"
    shutil.copytree(raw, entrada / "ipeadata")
    _tira_o_que_nao_gera_parquet(entrada)
    lake = tmp_path / "lake"
    _legacy_convert(entrada / "ipeadata", lake, monkeypatch)
    converter.convert(entrada / "ipeadata", lake)

    report = lake_audit(lake, input_dir=entrada, converters={}, rehash=True)

    assert report.ok, report.to_text()


def _tira_o_que_nao_gera_parquet(entrada: Path) -> None:
    """Série vazia, estado do backfill e cópias antigas não geram Parquet próprio."""
    base = entrada / "ipeadata"
    (base / "macro" / "VAZIA@20261105.json").unlink()
    (base / "series" / "_seratualizacao.json").unlink()
    (base / "series" / "PRECOS_IPCAG@20261101.json").unlink()
    (base / "series" / "PRECOS_INPC@20261101.json").unlink(missing_ok=True)
    # Um arquivo em vários níveis territoriais (partição ``nivel=`` das linhas) é
    # apontado pela auditoria como duplicata, com o layout antigo e com o novo (ver
    # ``test_auditoria_acusa_varios_niveis_nos_dois_layouts``): fica só um nível.
    adh = [_row("ADH_IDHM", f"{a}-01-01", 0.5, "Estados", "41") for a in (1991, 2000)]
    _write(base / "regional" / "ADH_IDHM@20261105.json", {"value": adh})


def test_auditoria_acusa_varios_niveis_nos_dois_layouts(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um arquivo bruto repartido por ``nivel=`` das linhas é ``versao_duplicada`` na
    auditoria, antes e depois do agrupamento: a mudança não cria nem tira o achado."""
    entrada = tmp_path / "entrada"
    shutil.copytree(raw, entrada / "ipeadata")
    (entrada / "ipeadata/macro/VAZIA@20261105.json").unlink()
    (entrada / "ipeadata/series/_seratualizacao.json").unlink()
    (entrada / "ipeadata/series/PRECOS_IPCAG@20261101.json").unlink()
    (entrada / "ipeadata/series/PRECOS_INPC@20261101.json").unlink(missing_ok=True)

    antigo = tmp_path / "lake_antigo"
    _legacy_convert(entrada / "ipeadata", antigo, monkeypatch)
    novo = tmp_path / "lake_novo"
    converter.convert(entrada / "ipeadata", novo)

    def achados(lake: Path) -> list[str]:
        rep = lake_audit(lake, input_dir=entrada, converters={}, rehash=True)
        return [f.message.split(" (")[0] for f in rep.findings]

    assert achados(antigo) == achados(novo) == ["ADH_IDHM@20261105.json"]


def test_conversao_nao_deixa_temporarios(
    raw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("QUANTILICA_LAKE_SCRATCH", str(scratch))
    lake = tmp_path / "lake"

    res = converter.convert(raw, lake)

    assert not res.errors
    # Só o diretório de derramamento do Polars (removido ao fim do processo).
    assert [p.name for p in scratch.iterdir() if not p.name.startswith("polars-")] == []
    assert not list(lake.rglob(".tmp"))


def test_force_reescreve_tudo_sem_duplicar(raw: Path, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    converter.convert(raw, lake)
    linhas = _linhas(lake).height
    n = len(_parquets(lake))

    res = converter.convert(raw, lake, force=True)

    assert not res.errors and res.converted == N_SERIES + DIM
    assert len(_parquets(lake)) == n
    assert _linhas(lake).height == linhas
