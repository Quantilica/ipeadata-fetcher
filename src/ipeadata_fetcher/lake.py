"""Universal Hive Parquet Lake converter for ipeadata-fetcher."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import unicodedata
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import polars as pl
    import pyarrow.parquet as pq
    from quantilica.analytics.lake import (
        META_MEMBERS,
        ConvertResult,
        GroupMember,
        LakeWriter,
        footer_from_metadata,
    )
    from quantilica.core.files import sha256_file
    from quantilica.core.lake import (
        DatasetDescriptor,
        file_key,
        partition_dir,
        partition_types_for,
        select_current,
    )
    from quantilica.core.manifests import MANIFEST_SIDECAR_SUFFIX
except ImportError as exc:
    raise ImportError(
        "ipeadata_fetcher.lake requer o extra 'analysis': "
        "uv add 'ipeadata-fetcher[analysis]' "
        "--index https://index.quantilica.com/simple/"
    ) from exc

logger = logging.getLogger(__name__)

SOURCE_ID = "ipeadata"
_DIMENSOES_BRUTO = ("metadados", "series", "temas", "territorios", "paises")
DATASETS = ["series", "temas", "territorios", "paises", "valores", "valores_regional"]
#: Partição dos valores: a primeira chave e a periodicidade vêm da série (ou do nível
#: territorial da linha) e ``ano`` vem da data de cada observação.
VALORES_KEYS = {
    "valores": ["base", "periodicidade", "ano"],
    "valores_regional": ["nivel", "periodicidade", "ano"],
}
#: Versões gravadas em cada membro de grupo; subir uma reconverte os valores.
CONTRACT_VERSION = 1
CONVERTER_VERSION = "1"


def _norm_col(col_name: str) -> str:
    s = unicodedata.normalize("NFKD", col_name)
    s = s.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _read_json_items(file_path: Path) -> list[dict[str, Any]]:
    """Read JSON file and return items list (handles OData wrapping)."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        items = data.get("value", [])
        if isinstance(items, list):
            return items
    elif isinstance(data, list):
        return data
    return []


def _partition_value(value: Any, *, lower: bool = False) -> str | None:
    """Valor de partição seguro (sem acento/espaço/barra); ``None`` se vazio.

    ``None`` vira ``__HIVE_DEFAULT_PARTITION__`` (quarentena) no lake.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii").strip()
    text = re.sub(r"[^A-Za-z0-9\-]+", "_", text).strip("_")
    if not text:
        return None
    return text.lower() if lower else text


def _periodicidades(meta_items: list[dict[str, Any]]) -> dict[str, str | None]:
    """``SERCODIGO -> periodicidade`` (``PERNOME`` do OData) normalizada."""
    result: dict[str, str | None] = {}
    for item in meta_items:
        code = item.get("SERCODIGO")
        if code:
            result[str(code)] = _partition_value(
                item.get("PERNOME") or item.get("SERPERIODICIDADE"), lower=True
            )
    return result


#: Pastas do bruto que guardam valores; em empate de carimbo vence a primeira.
_PRIORIDADE_PASTAS = ("regional", "social", "macro", "series")


def _mais_recente_entre_pastas(files: Sequence[Path]) -> tuple[list[Path], list[Path]]:
    """Uma só cópia por série, mesmo que ela exista em mais de uma pasta.

    ``select_current`` escolhe a versão mais recente dentro de cada pasta, mas a
    mesma série (``SERCODIGO``) pode ter arquivo em ``macro/`` e ``series/``, ou
    em ``series/``, ``regional/`` e ``social/``. Todas as cópias vão para o mesmo
    destino do lake (``<SERCODIGO>.parquet``), e a última pasta em ordem
    alfabética sobrescrevia as outras, mesmo sendo a mais antiga. Aqui vence o
    carimbo (``@AAAAMMDD[THHMMSS]``) mais recente; sem carimbo, a cópia perde
    de qualquer outra. Devolve ``(mantidos, descartados)``.
    """
    por_nome = {}
    for f in files:
        por_nome.setdefault(f.name, []).append(f)
    # ``select_current`` ordena as versões pelo carimbo do nome: passa só os
    # nomes, numa pasta única, para compará-las entre as pastas.
    vencedores = {
        PurePosixPath(n).name
        for n in select_current([PurePosixPath("v") / nome for nome in por_nome])
    }
    por_chave: dict[str, list[Path]] = {}
    for nome in vencedores:
        for f in por_nome[nome]:
            por_chave.setdefault(file_key(f), []).append(f)

    def prioridade(f: Path) -> tuple[int, str]:
        pasta = f.parent.name.lower()
        rank = (
            _PRIORIDADE_PASTAS.index(pasta)
            if pasta in _PRIORIDADE_PASTAS
            else len(_PRIORIDADE_PASTAS)
        )
        return rank, str(f)

    mantidos = {min(fs, key=prioridade) for fs in por_chave.values()}
    return (
        [f for f in files if f in mantidos],
        [f for f in files if f not in mantidos],
    )


def _with_ativa(df: pl.DataFrame) -> pl.DataFrame:
    """Coluna ``ativa`` (bool) de ``serstatus``: ``A`` ou ausente é ativa."""
    if "serstatus" not in df.columns:
        return df.with_columns(pl.lit(True).alias("ativa"))
    status = pl.col("serstatus").cast(pl.Utf8).str.strip_chars().str.to_uppercase()
    return df.with_columns(
        status.is_in(["A", ""]).fill_null(True).alias("ativa"),
    )


class IpeadataLakeConverter:
    """Converts Ipeadata JSON snapshots and series into Universal Hive Parquet Lake."""

    def __init__(self, source_id: str = SOURCE_ID) -> None:
        self.source_id = source_id

    def datasets(self) -> list[str]:
        """Return available dataset identifiers."""
        return list(DATASETS)

    def convert(
        self,
        input_dir: Path,
        lake_dir: Path,
        *,
        datasets: Sequence[str] | None = None,
        force: bool = False,
    ) -> ConvertResult:
        res = ConvertResult()
        input_path = Path(input_dir)
        lake_path = Path(lake_dir)

        if not input_path.exists():
            return res

        target_datasets = set(datasets or DATASETS)

        # Initialize writers for dimensions (unpartitioned)
        writers: dict[str, LakeWriter] = {}
        for dim in ("series", "temas", "territorios", "paises"):
            if dim in target_datasets:
                desc = DatasetDescriptor(
                    source_id=self.source_id,
                    dataset_id=dim,
                    alias=dim,
                    partition_keys=[],
                    partition_types={},
                )
                writers[dim] = LakeWriter(
                    lake_path / self.source_id / dim, desc, force=force
                )

        # Initialize writers for values
        if "valores" in target_datasets:
            desc_val = DatasetDescriptor(
                source_id=self.source_id,
                dataset_id="valores",
                alias="valores",
                partition_keys=VALORES_KEYS["valores"],
                partition_types=partition_types_for(VALORES_KEYS["valores"]),
            )
            writers["valores"] = LakeWriter(
                lake_path / self.source_id / "valores", desc_val, force=force
            )

        if "valores_regional" in target_datasets:
            desc_reg = DatasetDescriptor(
                source_id=self.source_id,
                dataset_id="valores_regional",
                alias="valores_regional",
                partition_keys=VALORES_KEYS["valores_regional"],
                partition_types=partition_types_for(VALORES_KEYS["valores_regional"]),
            )
            writers["valores_regional"] = LakeWriter(
                lake_path / self.source_id / "valores_regional", desc_reg, force=force
            )

        # Find current raw files
        # Os sidecars ``.manifest.json`` acompanham o bruto e não são dados.
        all_raw_files = [
            f
            for f in input_path.rglob("*.json")
            if f.is_file()
            and not f.name.endswith(MANIFEST_SIDECAR_SUFFIX)
            # estado interno do fetcher (``_seratualizacao.json``), não é dado
            and not f.name.startswith("_")
        ]
        active_files = select_current(all_raw_files)
        # A mesma série em mais de uma pasta tem um só destino no lake: fica a
        # cópia mais recente.
        dimensoes = [f for f in active_files if file_key(f).lower() in _DIMENSOES_BRUTO]
        candidatos_valores = [f for f in active_files if f not in dimensoes]
        # Pastas em que cada série existe: o destino no lake depende delas e não
        # da pasta da cópia que venceu, para não mudar de partição (e duplicar
        # linhas) quando a cópia mais nova passa de uma pasta para outra.
        pastas_da_serie: dict[str, set[str]] = {}
        for f in candidatos_valores:
            pastas_da_serie.setdefault(file_key(f), set()).add(f.parent.name.lower())
        valores_brutos, repetidos = _mais_recente_entre_pastas(candidatos_valores)
        for repetido in repetidos:
            logger.info(
                "Ipeadata %s/%s: há cópia mais recente da série em outra pasta; "
                "ignorada",
                repetido.parent.name,
                repetido.name,
            )
        active_files = sorted(dimensoes + valores_brutos)

        # Periodicidade real de cada serie, do arquivo de metadados (PERNOME).
        periodicidades: dict[str, str | None] = {}
        for raw_file in active_files:
            if file_key(raw_file).lower() in ("metadados", "series"):
                periodicidades.update(_periodicidades(_read_json_items(raw_file)))

        # First convert dimensions
        for raw_file in active_files:
            stem = file_key(raw_file).lower()
            dim_key = None
            if stem in ("metadados", "series"):
                dim_key = "series"
            elif stem in ("temas", "territorios", "paises"):
                dim_key = stem

            if dim_key and dim_key in writers:
                items = _read_json_items(raw_file)
                if not items:
                    continue
                try:
                    df = pl.DataFrame(items, infer_schema_length=None)
                    df = df.rename({c: _norm_col(c) for c in df.columns})
                    if dim_key == "series":
                        df = _with_ativa(df)
                    writers[dim_key].write_polars(df, src=raw_file)
                    res.converted += 1
                except Exception as exc:
                    res.errors.append(f"Erro ao converter dimensão {dim_key}: {exc}")

        # Valores: um Parquet por (dataset, base|nivel, periodicidade, ano), com todas
        # as séries que têm observações naquele ano.
        _convert_valores(
            [
                f
                for f in active_files
                if file_key(f).lower() not in _DIMENSOES_BRUTO and f.is_file()
            ],
            writers,
            periodicidades,
            pastas_da_serie,
            res,
        )

        return res


@dataclass
class _Prepared:
    """Uma série pronta para o lake: linhas normalizadas e destino de cada uma."""

    df: pl.DataFrame
    dataset: str
    periodicidade: str | None
    #: coluna da primeira chave de partição em ``df`` (``base`` ou ``nivel``)
    chave: str


def _year(data: pl.Expr) -> pl.Expr:
    """Ano (int) dos 4 primeiros caracteres de ``data``; nulo se não for AAAA-."""
    return (
        pl.when(data.str.contains(r"^\d{4}-"))
        .then(data.str.slice(0, 4).cast(pl.Int64))
        .otherwise(None)
    )


def _prepare_series(
    raw_file: Path,
    pastas: set[str],
    periodicidades: dict[str, str | None],
    *,
    quiet: bool = False,
) -> _Prepared | None:
    """Lê e normaliza o JSON de uma série; ``None`` se não há o que converter.

    Colunas: as do JSON em minúsculas, mais ``data`` (AAAA-MM-DD), ``valor`` e as de
    partição (``base`` ou ``nivel``, ``periodicidade`` e ``ano``). Os tipos das colunas
    conhecidas são fixados (texto, e ``valvalor`` decimal quando numérico), porque um
    grupo guarda um esquema só e séries só com valores inteiros inferiam ``Int64``.
    """
    log = logger.debug if quiet else logger.warning
    items = _read_json_items(raw_file)
    if not items:
        log(
            "Ipeadata %s/%s: série sem nenhum valor (lista vazia); nada a converter",
            raw_file.parent.name,
            raw_file.name,
        )
        return None
    df = pl.DataFrame(items, infer_schema_length=None)
    df = df.rename({c: _norm_col(c) for c in df.columns})
    if "valdata" not in df.columns or "valvalor" not in df.columns:
        log(
            "Ipeadata %s/%s: resposta sem VALDATA e VALVALOR; série ignorada",
            raw_file.parent.name,
            raw_file.name,
        )
        return None

    # Tipos: texto nas colunas de texto; valvalor decimal se numérico (ou todo nulo).
    textos = [
        c for c in ("sercodigo", "valdata", "nivnome", "tercodigo") if c in df.columns
    ]
    df = df.with_columns(*(pl.col(c).cast(pl.Utf8) for c in textos))
    if df.schema["valvalor"].is_numeric() or df.schema["valvalor"] == pl.Null:
        df = df.with_columns(pl.col("valvalor").cast(pl.Float64))

    # 1. Date: extract YYYY-MM-DD string slice (no fuso shift)
    df = df.with_columns(pl.col("valdata").str.slice(0, 10).alias("data"))
    # 2. Value: Float64
    df = df.with_columns(
        pl.col("valvalor").cast(pl.Float64, strict=False).alias("valor")
    )
    # 3. Clean empty strings in nivnome and tercodigo to null
    for col in ("nivnome", "tercodigo"):
        if col in df.columns:
            df = df.with_columns(
                pl.when(pl.col(col).str.strip_chars() == "")
                .then(None)
                .otherwise(pl.col(col))
                .alias(col)
            )
        else:
            df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(col))

    # Determine whether regional or macro/social:
    has_nivel = df.select(pl.col("nivnome").is_not_null().any()).item()
    is_regional = "regional" in pastas or bool(has_nivel)

    # Periodicidade vem dos metadados da serie, nunca fixa.
    sercodigo = file_key(raw_file)
    if "sercodigo" in df.columns:
        codes = df["sercodigo"].drop_nulls().unique().to_list()
        if len(codes) == 1:
            sercodigo = str(codes[0])
    periodicidade = periodicidades.get(sercodigo)
    if periodicidade is None:
        log(
            "Ipeadata %s: sem periodicidade nos metadados; particao de "
            "quarentena periodicidade=__HIVE_DEFAULT_PARTITION__",
            raw_file.name,
        )
    df = df.with_columns(
        pl.lit(periodicidade, dtype=pl.Utf8).alias("periodicidade"),
        _year(pl.col("data")).alias("ano"),
    )
    if df["ano"].null_count():
        log(
            "Ipeadata %s: %d linha(s) sem data AAAA-MM-DD na particao de "
            "quarentena ano=__HIVE_DEFAULT_PARTITION__",
            raw_file.name,
            df["ano"].null_count(),
        )
    if is_regional:
        # Nivel territorial real por linha (um arquivo mistura
        # Municipios, AMC..., Estados, Brasil).
        df = df.with_columns(
            pl.col("nivnome")
            .map_elements(_partition_value, return_dtype=pl.Utf8)
            .alias("nivel")
        )
        if not quiet and df["nivel"].null_count():
            logger.warning(
                "Ipeadata %s: %d linha(s) sem NIVNOME na particao de "
                "quarentena nivel=__HIVE_DEFAULT_PARTITION__",
                raw_file.name,
                df["nivel"].null_count(),
            )
        return _Prepared(df, "valores_regional", periodicidade, "nivel")
    base = "social" if "social" in pastas else "macro"
    return _Prepared(
        df.with_columns(pl.lit(base).alias("base")), "valores", periodicidade, "base"
    )


@dataclass
class _Serie:
    """O que se sabe de uma série do bruto antes de escrever qualquer grupo."""

    raw_file: Path
    key: str
    sha256: str
    pastas: set[str]
    dataset: str
    #: (primeira chave, periodicidade, ano) -> número de linhas
    destinos: dict[tuple[str | None, str | None, int | None], int]
    ok: bool = True
    escrita: bool = False


class _Slices:
    """Fatias por grupo de cada série, em Parquet temporário, geradas sob demanda.

    Uma série entra em um grupo por ano; reler e normalizar o JSON para cada ano seria
    quadrático. A primeira vez que um grupo pede a série, ela é lida uma vez e
    gravada em fatias (uma por destino); os grupos seguintes só leem a fatia. O
    diretório sai ao fim da conversão.
    """

    def __init__(self, periodicidades: dict[str, str | None]) -> None:
        self._tmp = tempfile.TemporaryDirectory(
            prefix="ipeadata-",
            dir=os.environ.get("QUANTILICA_LAKE_SCRATCH") or None,
        )
        self.periodicidades = periodicidades
        self._done: dict[Path, dict[tuple, Path]] = {}

    def close(self) -> None:
        self._tmp.cleanup()

    def get(self, serie: _Serie, destino: tuple) -> Path:
        fatias = self._done.get(serie.raw_file)
        if fatias is None:
            prepared = _prepare_series(
                serie.raw_file, serie.pastas, self.periodicidades, quiet=True
            )
            if prepared is None:
                raise ValueError(f"{serie.raw_file.name}: sem linhas na releitura")
            fatias = {}
            pasta = Path(self._tmp.name) / f"{len(self._done):06d}"
            pasta.mkdir()
            df = prepared.df
            chaves = [prepared.chave, "periodicidade", "ano"]
            for i, (valores, part) in enumerate(
                df.partition_by(chaves, as_dict=True, maintain_order=True).items()
            ):
                path = pasta / f"{i:05d}.parquet"
                part.drop(chaves).write_parquet(path, compression="zstd")
                fatias[valores] = path
            self._done[serie.raw_file] = fatias
        return fatias[destino]


def _slug(value: Any) -> str:
    return "sem" if value is None else str(value)


def _convert_valores(
    raw_files: Sequence[Path],
    writers: dict[str, LakeWriter],
    periodicidades: dict[str, str | None],
    pastas_da_serie: dict[str, set[str]],
    res: ConvertResult,
) -> None:
    """Valores das séries em grupos por ano (``LakeWriter.write_group``).

    Primeiro lê cada série uma vez e só guarda onde suas linhas caem (dataset,
    base ou nível, periodicidade e ano). A lista de membros de um grupo é, então,
    o conjunto das séries vigentes com linhas naquele destino e ano: uma série
    revisada que perdeu as linhas de um ano sai do grupo daquele ano, e a que
    entrou nele passa a constar. Só então escreve: o grupo cujos membros não mudaram
    é pulado sem reescrever, e do que mudou só a série alterada é relida.
    """
    series: list[_Serie] = []
    inspection_failed = False
    for raw_file in raw_files:
        key = file_key(raw_file)
        pastas = pastas_da_serie.get(key, set())
        try:
            prepared = _prepare_series(raw_file, pastas, periodicidades)
            if prepared is None:
                res.skipped += 1
                continue
            if prepared.dataset not in writers:
                continue
            contagem = prepared.df.group_by(
                [prepared.chave, "periodicidade", "ano"]
            ).len()
            destinos = {(p1, per, ano): n for p1, per, ano, n in contagem.iter_rows()}
            series.append(
                _Serie(
                    raw_file,
                    key,
                    sha256_file(raw_file),
                    pastas,
                    prepared.dataset,
                    destinos,
                )
            )
        except Exception as exc:
            res.errors.append(f"Erro ao converter série {raw_file.name}: {exc}")
            inspection_failed = True

    grupos: dict[tuple[str, str | None, str | None, int | None], list[_Serie]] = {}
    for serie in sorted(series, key=lambda x: x.key):
        for p1, per, ano in serie.destinos:
            grupos.setdefault((serie.dataset, p1, per, ano), []).append(serie)

    slices = _Slices(periodicidades)
    planned: dict[str, set[Path]] = {d: set() for d in writers}
    dataset_failed: set[str] = set()
    try:
        for (dataset, p1, per, ano), membros in sorted(
            grupos.items(), key=lambda kv: tuple(map(_slug, kv[0]))
        ):
            writer = writers.get(dataset)
            if writer is None:
                continue
            keys = VALORES_KEYS[dataset]
            partitions = {keys[0]: p1, keys[1]: per, keys[2]: ano}
            # Sem o ano no nome: o mesmo nome em cada ``ano=`` é o que a auditoria do
            # lake reconhece como uma série repartida por ano das linhas.
            group_key = "_".join([dataset, _slug(p1), _slug(per)])
            planned[dataset].add(
                partition_dir(writer.dataset_dir, partitions) / f"{group_key}.parquet"
            )

            def fatia(serie: _Serie, destino=(p1, per, ano)):
                return lambda: slices.get(serie, destino)

            group = [
                GroupMember(
                    s.raw_file,
                    fatia(s),
                    key=s.key,
                    sha256=s.sha256,
                )
                for s in membros
            ]
            options = {
                "partitions": partitions,
                "contract_version": CONTRACT_VERSION,
                "converter_version": CONVERTER_VERSION,
                "prune": not inspection_failed,
            }
            try:
                if not writer.is_current_group(group_key, group, **options):
                    result = writer.write_group(
                        group_key,
                        group,
                        converter="ipeadata-fetcher",
                        sort_by=["sercodigo", "data"],
                        **options,
                    )
                    for s in membros:
                        if s.key in result.written:
                            s.escrita = True
            except Exception as exc:
                dataset_failed.add(dataset)
                for s in membros:
                    s.ok = False
                res.errors.append(f"Erro ao converter grupo {group_key}: {exc}")
    finally:
        slices.close()

    for s in series:
        if s.escrita:
            res.converted += 1
        else:
            res.skipped += 1 if s.ok else 0
    keys_atuais = {s.key for s in series}
    for dataset, writer in writers.items():
        if dataset not in VALORES_KEYS:
            continue
        _remove_legacy_series(
            writer.dataset_dir, dataset, {s.key for s in series if s.ok}
        )
        if not inspection_failed and dataset not in dataset_failed:
            _drop_stale_groups(
                writer.dataset_dir, dataset, planned[dataset], keys_atuais
            )


def _footer(path: Path) -> dict[str, str] | None:
    try:
        return footer_from_metadata(pq.ParquetFile(path).metadata)
    except Exception:
        return None


def _prune_empty_dirs(directory: Path, stop: Path) -> None:
    while directory != stop and directory.is_dir():
        with suppress(OSError):
            directory.rmdir()
        if directory.exists():
            return
        directory = directory.parent


def _remove_legacy_series(dataset_dir: Path, dataset: str, keys: set[str]) -> int:
    """Apaga os Parquets por série do layout anterior (``<chave>/periodicidade=/``).

    Antes, cada série tinha o próprio ``<SERCODIGO>.parquet`` direto na pasta da
    periodicidade (``base=macro/periodicidade=mensal/``, ``nivel=Estados/...``).
    Todas as linhas da série estão agora nos grupos por ano, então esse arquivo,
    escrito por este dataset e não agrupado, sai. Só de séries cujos grupos foram
    todos escritos ou conferidos nesta execução (``keys``). Devolve quantos apagou.
    """
    removed = 0
    for path in sorted(dataset_dir.glob("*/*/*.parquet")):
        meta = _footer(path)
        if (
            meta is None
            or meta.get("quantilica.source_id") != SOURCE_ID
            or meta.get("quantilica.dataset_id") != dataset
            or META_MEMBERS in meta
            or meta.get("quantilica.file_key") not in keys
            or meta.get("quantilica.file_key") != path.stem
        ):
            continue
        path.unlink()
        removed += 1
        _prune_empty_dirs(path.parent, dataset_dir)
    return removed


def _drop_stale_groups(
    dataset_dir: Path, dataset: str, planned: set[Path], keys: set[str]
) -> list[Path]:
    """Apaga arquivos agrupados que nenhum grupo atual gera, sem perder linhas.

    Um grupo que sai do plano (a série mudou de periodicidade ou de nível, ou
    perdeu todas as linhas de um ano numa revisão) deixaria as linhas antigas em
    duplicidade com o novo destino. Só é apagado se todos os membros dele ainda
    são séries do bruto (as linhas estão nos grupos novos); senão fica, com aviso.
    """
    gone: list[Path] = []
    for path in sorted(dataset_dir.glob("*/*/ano=*/*.parquet")):
        if path in planned:
            continue
        meta = _footer(path)
        if (
            meta is None
            or meta.get("quantilica.source_id") != SOURCE_ID
            or meta.get("quantilica.dataset_id") != dataset
            or META_MEMBERS not in meta
        ):
            continue
        membros = json.loads(meta[META_MEMBERS])
        if all(k in keys for k in membros):
            path.unlink()
            gone.append(path)
            logger.info("Ipeadata: grupo obsoleto %s removido", path)
            _prune_empty_dirs(path.parent, dataset_dir)
        else:
            logger.warning(
                "Ipeadata: %s fora do plano, com séries ausentes do bruto; mantido",
                path,
            )
    return gone


converter = IpeadataLakeConverter()
