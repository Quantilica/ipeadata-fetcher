"""Brutos sintéticos do Ipeadata e retrato do lake, para a prova de equivalência.

``build_raw`` monta, no formato do fetcher (``<pasta>/<SERCODIGO>@<AAAAMMDD>.json``,
OData ``{"value": [...]}``), séries que cobrem o que o conversor trata: mensais,
anuais, diárias e decenais em vários anos, uma série só com valores inteiros, uma
série sem periodicidade nos metadados (quarentena), regionais com vários níveis
territoriais, a mesma série em duas pastas com carimbos diferentes, série vazia e
o arquivo de estado do backfill.

``snapshot`` descreve o lake lendo cada Parquet direto (sem hive), por dataset e
por partição lógica (``base`` ou ``nivel`` e ``periodicidade``), que é a mesma nos
dois layouts: número de linhas, colunas e tipos, anos das datas, hash do conteúdo
ordenado e uma amostra. A única diferença de tipo que o agrupamento introduz é
``valvalor`` inteiro virar ``double`` (um grupo tem um esquema só); o retrato
normaliza essa coluna para ``Float64`` e guarda à parte o tipo que o arquivo tinha.
``golden/lake_antes_do_agrupamento.json`` foi gerado pelo conversor de um Parquet por
série, antes da mudança:

    uv run --no-sync python -m tests.lake_fixtures --escrever-golden
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

GOLDEN = Path(__file__).parent / "golden" / "lake_antes_do_agrupamento.json"

META = {
    "value": [
        {"SERCODIGO": "PRECOS_IPCAG", "SERNOME": "IPCA", "PERNOME": "Mensal"},
        {"SERCODIGO": "PRECOS_INPC", "SERNOME": "INPC", "PERNOME": "Mensal"},
        {"SERCODIGO": "PRECOS_ANO", "SERNOME": "Inteiros", "PERNOME": "Mensal"},
        {"SERCODIGO": "PIB_ANUAL", "SERNOME": "PIB", "PERNOME": "Anual"},
        {"SERCODIGO": "CAMBIO_D", "SERNOME": "Câmbio", "PERNOME": "Diária"},
        {"SERCODIGO": "ADH_IDHM", "SERNOME": "IDHM", "PERNOME": "Decenal"},
        {"SERCODIGO": "DFEDUCM", "SERNOME": "Educação", "PERNOME": "Anual"},
        {"SERCODIGO": "SOC_X", "SERNOME": "Social", "PERNOME": "Anual"},
    ]
}


def _row(
    code: str, data: str, valor: float | None, niv: str = "", ter: str = ""
) -> dict:
    return {
        "SERCODIGO": code,
        "VALDATA": f"{data}T00:00:00-03:00",
        "VALVALOR": valor,
        "NIVNOME": niv,
        "TERCODIGO": ter,
    }


def _mensal(code: str, anos: range, base: float) -> list[dict]:
    return [
        _row(code, f"{a}-{m:02d}-01", round(base + a % 100 + m / 10, 2))
        for a in anos
        for m in range(1, 13)
    ]


def _diaria(code: str) -> list[dict]:
    dias = [
        "2019-12-30",
        "2019-12-31",
        "2020-01-02",
        "2020-06-15",
        "2021-01-04",
        "2021-12-30",
    ]
    return [_row(code, d, None if i == 2 else 4.0 + i / 7) for i, d in enumerate(dias)]


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def build_raw(root: Path) -> None:
    """Cria o bruto sob ``root``."""
    _write(root / "dimensoes" / "metadados@20261101.json", META)
    _write(
        root / "macro" / "PRECOS_IPCAG@20261105.json",
        {"value": _mensal("PRECOS_IPCAG", range(2019, 2023), 100.0)},
    )
    # a mesma série também em series/, com carimbo mais antigo e menos anos: ignorada
    _write(
        root / "series" / "PRECOS_IPCAG@20261101.json",
        {"value": _mensal("PRECOS_IPCAG", range(2019, 2020), 100.0)},
    )
    _write(
        root / "series" / "PRECOS_INPC@20261105.json",
        {"value": _mensal("PRECOS_INPC", range(2020, 2022), 50.0)},
    )
    # mesma série em duas pastas, com carimbos diferentes: vale a mais recente
    _write(
        root / "series" / "PRECOS_INPC@20261101.json",
        {"value": _mensal("PRECOS_INPC", range(2020, 2021), 50.0)},
    )
    # série só com valores inteiros (valvalor Int64 no conversor antigo)
    inteiros = [
        _row("PRECOS_ANO", f"{a}-{m:02d}-01", a % 100 + m)
        for a in (2020, 2021)
        for m in (1, 2, 3)
    ]
    _write(root / "macro" / "PRECOS_ANO@20261105.json", {"value": inteiros})
    _write(
        root / "macro" / "PIB_ANUAL@20261105.json",
        {
            "value": [
                _row("PIB_ANUAL", f"{a}-01-01", a / 1000) for a in range(1950, 2024)
            ]
        },
    )
    _write(root / "series" / "CAMBIO_D@20261105.json", {"value": _diaria("CAMBIO_D")})
    # sem periodicidade nos metadados: quarentena
    _write(
        root / "macro" / "SEM_META@20261105.json",
        {"value": [_row("SEM_META", f"{a}-01-01", 1.5) for a in (2020, 2021)]},
    )
    # série sem nenhum valor e arquivo de estado do backfill
    _write(root / "macro" / "VAZIA@20261105.json", {"value": []})
    _write(root / "series" / "_seratualizacao.json", {"PIB_ANUAL": "2026-11-01"})
    # regional: vários níveis e anos num arquivo só
    regional = []
    for a in (1991, 2000, 2010):
        for nivel, terr in (
            ("Municípios", "3550308"),
            ("Municípios", "4118402"),
            ("Estados", "41"),
            ("AMC 91-00", "99"),
            ("Brasil", "1"),
        ):
            regional.append(
                _row("ADH_IDHM", f"{a}-01-01", 0.4 + a / 10000, nivel, terr)
            )
    _write(root / "regional" / "ADH_IDHM@20261105.json", {"value": regional})
    _write(
        root / "regional" / "DFEDUCM@20261105.json",
        {
            "value": [
                _row(
                    "DFEDUCM",
                    f"{a}-01-01",
                    1500.5 * (a - 2000),
                    "Municípios",
                    "3550308",
                )
                for a in (2019, 2020, 2021)
            ]
        },
    )
    # social: os valores têm NIVNOME, vão para valores_regional (como em produção)
    _write(
        root / "social" / "SOC_X@20261105.json",
        {
            "value": [
                _row("SOC_X", f"{a}-01-01", a % 7, "Estados", "35")
                for a in (2000, 2001)
            ]
        },
    )


def _sha(linhas: list[list[str]]) -> str:
    return hashlib.sha256(
        json.dumps(linhas, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _chaves(arquivo: Path, base: Path) -> dict[str, str]:
    return dict(
        p.split("=", 1) for p in arquivo.relative_to(base).parts[:-1] if "=" in p
    )


def snapshot(lake_dir: Path) -> dict[str, Any]:
    """Retrato do lake por dataset e partição lógica, independente do layout."""
    import polars as pl

    saida: dict[str, Any] = {}
    for dataset, chave in (("valores", "base"), ("valores_regional", "nivel")):
        base = lake_dir / "ipeadata" / dataset
        acumulado: dict[str, dict[str, Any]] = {}
        for arquivo in sorted(base.rglob("*.parquet")):
            chaves = _chaves(arquivo, base)
            df = pl.read_parquet(arquivo, hive_partitioning=False)
            if "_origem" in df.columns:
                df = df.drop("_origem")
            tipo_valvalor = str(df.schema["valvalor"])
            df = df.with_columns(pl.col("valvalor").cast(pl.Float64))
            anos = set(df["data"].str.slice(0, 4).unique().to_list())
            if "ano" in chaves:
                assert anos <= {chaves["ano"]}, (arquivo, anos)  # um ano por arquivo
            df = df.select(sorted(df.columns))
            slot = acumulado.setdefault(
                f"{chaves[chave]}/{chaves['periodicidade']}",
                {
                    "linhas": 0,
                    "arquivos": 0,
                    "anos": set(),
                    "conteudo": [],
                    "tipos": set(),
                },
            )
            slot["linhas"] += df.height
            slot["arquivos"] += 1
            slot["anos"] |= anos
            slot["tipos"].add(tipo_valvalor)
            slot["colunas"] = [[c, str(t)] for c, t in df.schema.items()]
            slot["conteudo"].extend(
                ["" if v is None else str(v) for v in row] for row in df.rows()
            )
        saida[dataset] = {}
        for particao, dados in sorted(acumulado.items()):
            conteudo = sorted(dados["conteudo"])
            saida[dataset][particao] = {
                "linhas": dados["linhas"],
                "colunas": dados["colunas"],
                "anos": sorted(dados["anos"]),
                "tipos_de_valvalor_no_arquivo": sorted(dados["tipos"]),
                "conteudo_sha256": _sha(conteudo),
                "amostra": conteudo[:3],
            }
    return saida


def contagem_de_arquivos(lake_dir: Path) -> dict[str, dict[str, int]]:
    """Parquets por dataset e partição lógica (``base|nivel/periodicidade``)."""
    saida: dict[str, dict[str, int]] = {}
    for dataset, chave in (("valores", "base"), ("valores_regional", "nivel")):
        base = lake_dir / "ipeadata" / dataset
        contagem: dict[str, int] = {}
        for arquivo in sorted(base.rglob("*.parquet")):
            c = _chaves(arquivo, base)
            k = f"{c[chave]}/{c['periodicidade']}"
            contagem[k] = contagem.get(k, 0) + 1
        saida[dataset] = dict(sorted(contagem.items()))
    return saida


def _escrever_golden() -> None:
    from ipeadata_fetcher.lake import converter

    with tempfile.TemporaryDirectory(prefix="ipeadata-golden-") as tmp:
        raiz = Path(tmp)
        build_raw(raiz / "raw")
        resultado = converter.convert(raiz / "raw", raiz / "lake")
        assert not resultado.errors, resultado.errors
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(
                {
                    "convertidos": resultado.converted,
                    "puladas": resultado.skipped,
                    "contagem_de_arquivos": contagem_de_arquivos(raiz / "lake"),
                    "lake": snapshot(raiz / "lake"),
                },
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"golden escrito em {GOLDEN}")


if __name__ == "__main__":
    if "--escrever-golden" not in sys.argv:
        raise SystemExit(__doc__)
    _escrever_golden()
