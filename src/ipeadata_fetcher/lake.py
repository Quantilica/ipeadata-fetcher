"""Universal Hive Parquet Lake converter for ipeadata-fetcher."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import polars as pl
    from quantilica.analytics.lake import ConvertResult, LakeWriter
    from quantilica.core.lake import (
        DatasetDescriptor,
        file_key,
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
                partition_keys=["base", "periodicidade"],
                partition_types=partition_types_for(["base", "periodicidade"]),
            )
            writers["valores"] = LakeWriter(
                lake_path / self.source_id / "valores", desc_val, force=force
            )

        if "valores_regional" in target_datasets:
            desc_reg = DatasetDescriptor(
                source_id=self.source_id,
                dataset_id="valores_regional",
                alias="valores_regional",
                partition_keys=["nivel", "periodicidade"],
                partition_types=partition_types_for(["nivel", "periodicidade"]),
            )
            writers["valores_regional"] = LakeWriter(
                lake_path / self.source_id / "valores_regional", desc_reg, force=force
            )

        # Find current raw files
        # Os sidecars ``.manifest.json`` acompanham o bruto e não são dados.
        all_raw_files = [
            f
            for f in input_path.rglob("*.json")
            if f.is_file() and not f.name.endswith(MANIFEST_SIDECAR_SUFFIX)
        ]
        active_files = select_current(all_raw_files)
        # A mesma série em mais de uma pasta tem um só destino no lake: fica a
        # cópia mais recente.
        dimensoes = [f for f in active_files if file_key(f).lower() in _DIMENSOES_BRUTO]
        valores_brutos, repetidos = _mais_recente_entre_pastas(
            [f for f in active_files if f not in dimensoes]
        )
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

        # Now convert series values
        for raw_file in active_files:
            stem = file_key(raw_file)
            stem_lower = stem.lower()
            if stem_lower in ("metadados", "series", "temas", "territorios", "paises"):
                continue

            items = _read_json_items(raw_file)
            if not items:
                logger.warning(
                    "Ipeadata %s/%s: série sem nenhum valor (lista vazia); "
                    "nada a converter",
                    raw_file.parent.name,
                    raw_file.name,
                )
                res.skipped += 1
                continue

            try:
                df = pl.DataFrame(items, infer_schema_length=None)
                df = df.rename({c: _norm_col(c) for c in df.columns})

                # Check essential columns: sercodigo, valdata, valvalor
                if "valdata" not in df.columns or "valvalor" not in df.columns:
                    logger.warning(
                        "Ipeadata %s/%s: resposta sem VALDATA e VALVALOR; "
                        "série ignorada",
                        raw_file.parent.name,
                        raw_file.name,
                    )
                    res.skipped += 1
                    continue

                # Normalizations:
                # 1. Date: extract YYYY-MM-DD string slice (no fuso shift)
                df = df.with_columns(
                    pl.col("valdata").cast(pl.Utf8).str.slice(0, 10).alias("data")
                )

                # 2. Value: Float64
                df = df.with_columns(
                    pl.col("valvalor").cast(pl.Float64, strict=False).alias("valor")
                )

                # 3. Clean empty strings in nivnome and tercodigo to null
                for col in ("nivnome", "tercodigo"):
                    if col in df.columns:
                        df = df.with_columns(
                            pl.when(pl.col(col).cast(pl.Utf8).str.strip_chars() == "")
                            .then(None)
                            .otherwise(pl.col(col))
                            .alias(col)
                        )
                    else:
                        df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(col))

                # Determine whether regional or macro/social:
                parent_group = raw_file.parent.name.lower()
                has_nivel = df.select(
                    pl.col("nivnome").cast(pl.Utf8).is_not_null().any()
                ).item()
                is_regional = parent_group == "regional" or bool(has_nivel)

                # Periodicidade vem dos metadados da serie, nunca fixa.
                sercodigo = file_key(raw_file)
                if "sercodigo" in df.columns:
                    codes = df["sercodigo"].drop_nulls().unique().to_list()
                    if len(codes) == 1:
                        sercodigo = str(codes[0])
                periodicidade = periodicidades.get(sercodigo)
                if periodicidade is None:
                    logger.warning(
                        "Ipeadata %s: sem periodicidade nos metadados; particao de "
                        "quarentena periodicidade=__HIVE_DEFAULT_PARTITION__",
                        raw_file.name,
                    )

                if is_regional and "valores_regional" in writers:
                    # Nivel territorial real por linha (um arquivo mistura
                    # Municipios, AMC..., Estados, Brasil).
                    df = df.with_columns(
                        pl.col("nivnome")
                        .cast(pl.Utf8)
                        .map_elements(_partition_value, return_dtype=pl.Utf8)
                        .alias("nivel"),
                        pl.lit(periodicidade, dtype=pl.Utf8).alias("periodicidade"),
                    )
                    for nivel in sorted(
                        df["nivel"].unique().to_list(), key=lambda v: (v is None, v)
                    ):
                        part = df.filter(
                            pl.col("nivel").is_null()
                            if nivel is None
                            else pl.col("nivel") == nivel
                        )
                        if nivel is None:
                            logger.warning(
                                "Ipeadata %s: %d linha(s) sem NIVNOME na particao "
                                "de quarentena nivel=__HIVE_DEFAULT_PARTITION__",
                                raw_file.name,
                                part.height,
                            )
                        writers["valores_regional"].write_polars(
                            part,
                            src=raw_file,
                            partitions={"nivel": nivel, "periodicidade": periodicidade},
                        )
                        res.converted += 1
                elif not is_regional and "valores" in writers:
                    base = "social" if parent_group == "social" else "macro"
                    df = df.with_columns(
                        pl.lit(base).alias("base"),
                        pl.lit(periodicidade, dtype=pl.Utf8).alias("periodicidade"),
                    )
                    writers["valores"].write_polars(
                        df,
                        src=raw_file,
                        partitions={"base": base, "periodicidade": periodicidade},
                    )
                    res.converted += 1
            except Exception as exc:
                res.errors.append(f"Erro ao converter série {raw_file.name}: {exc}")

        return res


converter = IpeadataLakeConverter()
