"""Universal Hive Parquet Lake converter for ipeadata-fetcher."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:
    import polars as pl
    from quantilica.analytics.lake import ConvertResult, LakeWriter
    from quantilica.core.lake import (
        DatasetDescriptor,
        partition_types_for,
        select_current,
    )
except ImportError as exc:
    raise ImportError(
        "ipeadata_fetcher.lake requer o extra 'analysis': "
        "uv add 'ipeadata-fetcher[analysis]' "
        "--index https://index.quantilica.com/simple/"
    ) from exc

SOURCE_ID = "ipeadata"
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
        all_raw_files = [f for f in input_path.rglob("*.json") if f.is_file()]
        active_files = select_current(all_raw_files)

        # First convert dimensions
        for raw_file in active_files:
            stem = raw_file.stem.split("@")[0].lower()
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
                    df = pl.DataFrame(items)
                    df = df.rename({c: _norm_col(c) for c in df.columns})
                    writers[dim_key].write_polars(df, src=raw_file)
                    res.converted += 1
                except Exception as exc:
                    res.errors.append(f"Erro ao converter dimensão {dim_key}: {exc}")

        # Now convert series values
        for raw_file in active_files:
            stem = raw_file.stem.split("@")[0]
            stem_lower = stem.lower()
            if stem_lower in ("metadados", "series", "temas", "territorios", "paises"):
                continue

            items = _read_json_items(raw_file)
            if not items:
                continue

            try:
                df = pl.DataFrame(items)
                df = df.rename({c: _norm_col(c) for c in df.columns})

                # Check essential columns: sercodigo, valdata, valvalor
                if "valdata" not in df.columns or "valvalor" not in df.columns:
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
                is_regional = parent_group == "regional" or any(
                    v is not None and v != "" for v in df["nivnome"].to_list()[:5]
                )

                if is_regional and "valores_regional" in writers:
                    nivel = "Municipios" if parent_group == "regional" else "Regional"
                    periodicidade = "mensal"
                    df = df.with_columns(
                        pl.lit(nivel).alias("nivel"),
                        pl.lit(periodicidade).alias("periodicidade"),
                    )
                    writers["valores_regional"].write_polars(
                        df,
                        src=raw_file,
                        partitions={"nivel": nivel, "periodicidade": periodicidade},
                    )
                    res.converted += 1
                elif not is_regional and "valores" in writers:
                    base = "social" if parent_group == "social" else "macro"
                    periodicidade = "mensal"
                    df = df.with_columns(
                        pl.lit(base).alias("base"),
                        pl.lit(periodicidade).alias("periodicidade"),
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
