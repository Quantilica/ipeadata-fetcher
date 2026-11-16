"""Prova de equivalência: os valores têm o mesmo conteúdo antes e depois do agrupamento.

``golden/lake_antes_do_agrupamento.json`` foi gerado pelo conversor de um Parquet por
série (commit anterior à mudança). Aqui o conversor atual lê os mesmos brutos e o
retrato do lake, por dataset e partição lógica (``base`` ou ``nivel`` e
``periodicidade``: linhas, colunas, anos, hash do conteúdo ordenado e amostra), tem de
ser idêntico. A única diferença admitida é de tipo: ``valvalor`` inteiro vira
``Float64``, porque um grupo tem um esquema só.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("quantilica.analytics.lake")

from ipeadata_fetcher.lake import converter  # noqa: E402

from .lake_fixtures import (  # noqa: E402
    GOLDEN,
    build_raw,
    contagem_de_arquivos,
    snapshot,
)


def _golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _viaje_json(obj: dict) -> dict:
    return json.loads(json.dumps(obj, ensure_ascii=False))


def test_conteudo_do_lake_igual_ao_do_conversor_anterior(tmp_path: Path) -> None:
    build_raw(tmp_path / "raw")
    res = converter.convert(tmp_path / "raw", tmp_path / "lake")
    assert not res.errors
    golden = _golden()
    # ``converted`` agora conta séries (o conversor anterior contava um arquivo por
    # série e nível: a ADH_IDHM, com 4 níveis, valia 4).
    assert (res.converted, res.skipped) == (
        golden["convertidos"] - 3,
        golden["puladas"],
    )

    atual = _viaje_json(snapshot(tmp_path / "lake"))

    assert sorted(atual) == sorted(golden["lake"])
    for dataset, particoes in golden["lake"].items():
        assert sorted(atual[dataset]) == sorted(particoes), dataset
        for particao, esperado in particoes.items():
            obtido = dict(atual[dataset][particao])
            # Só o tipo de valvalor no arquivo muda (Int64 -> Float64); o conteúdo,
            # lido como Float64 nos dois, é o mesmo.
            assert obtido.pop("tipos_de_valvalor_no_arquivo") == ["Float64"]
            esperado = dict(esperado)
            antes = esperado.pop("tipos_de_valvalor_no_arquivo")
            assert set(antes) <= {"Float64", "Int64"}
            assert obtido == esperado, (dataset, particao)


def test_um_parquet_por_particao_logica_e_ano(tmp_path: Path) -> None:
    build_raw(tmp_path / "raw")
    converter.convert(tmp_path / "raw", tmp_path / "lake")

    depois = contagem_de_arquivos(tmp_path / "lake")
    antes = _golden()["contagem_de_arquivos"]
    anos = {
        d: {p: len(x["anos"]) for p, x in v.items()}
        for d, v in _golden()["lake"].items()
    }

    assert sorted(depois) == sorted(antes)
    for dataset, particoes in depois.items():
        assert sorted(particoes) == sorted(antes[dataset])
        # Um Parquet por ano da partição, não por série.
        assert particoes == anos[dataset], dataset
    total_antes = sum(sum(p.values()) for p in antes.values())
    total_depois = sum(sum(p.values()) for p in depois.values())
    assert (total_antes, total_depois) == (12, 83 + 17)
    lake = tmp_path / "lake" / "ipeadata"
    assert (
        lake
        / "valores/base=macro/periodicidade=mensal/ano=2020"
        / "valores_macro_mensal.parquet"
    ).is_file()
    assert not list(lake.glob("valores*/*/*/*.parquet"))  # nada no layout antigo


def test_lake_profile_devolve_periodo_anual_dos_valores(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    from quantilica.core.lake_profile import profile_from_lake

    build_raw(tmp_path / "raw")
    converter.convert(tmp_path / "raw", tmp_path / "lake")
    lake = tmp_path / "lake"

    perfil = profile_from_lake(lake, "ipeadata", "valores_regional").perfil
    assert perfil["granularidade"] == "anual"
    assert perfil["periodos"] == [
        "1991",
        "2000",
        "2001",
        "2010",
        "2019",
        "2020",
        "2021",
    ]
    assert perfil["linhas"] == [5, 6, 1, 5, 1, 1, 1]
    assert perfil["colunas"]["valvalor"]["nulos"] == [0, 0, 0, 0, 0, 0, 0]

    perfil = profile_from_lake(lake, "ipeadata", "valores").perfil
    assert perfil["granularidade"] == "anual"
    assert perfil["periodos"][0] == "1950" and perfil["periodos"][-1] == "2023"
    assert "sercodigo" in perfil["colunas"] and "_origem" not in perfil["colunas"]
