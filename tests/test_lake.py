"""Tests for ipeadata-fetcher lake converter."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from quantilica.analytics.lake import check_dataset

from ipeadata_fetcher.lake import converter


def test_converter_metadata() -> None:
    assert converter.source_id == "ipeadata"
    datasets = converter.datasets()
    assert "series" in datasets
    assert "valores" in datasets
    assert "valores_regional" in datasets


def test_converter_empty_dir(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    lake_dir = tmp_path / "lake"
    lake_dir.mkdir()

    res = converter.convert(raw_dir, lake_dir)
    assert res.converted == 0
    assert not res.errors


def test_convert_ipeadata_end_to_end(tmp_path: Path) -> None:
    """Test conversion of dimensions and series values to Lake Hive."""
    raw_dir = tmp_path / "raw"
    dim_dir = raw_dir / "dimensoes"
    macro_dir = raw_dir / "macro"
    reg_dir = raw_dir / "regional"
    dim_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    reg_dir.mkdir(parents=True)

    lake_dir = tmp_path / "lake"
    lake_dir.mkdir()

    # 1. Dimension snapshot: metadados (converted to 'series')
    metadados_payload = {
        "value": [
            {
                "SERCODIGO": "PRECOS_IPCAG",
                "SERNOME": "IPCA Geral",
                "BASNOME": "Macroeconômico",
                "PERNOME": "Mensal",
            }
        ]
    }
    meta_file = dim_dir / "metadados@20261101.json"
    meta_file.write_text(json.dumps(metadados_payload), encoding="utf-8")

    # 2. Macro series values (converted to 'valores', base=macro/periodicidade=mensal)
    macro_payload = {
        "value": [
            {
                "SERCODIGO": "PRECOS_IPCAG",
                "VALDATA": "2024-01-01T00:00:00-02:00",
                "VALVALOR": 105.5,
                "NIVNOME": "",
                "TERCODIGO": "",
            },
            {
                "SERCODIGO": "PRECOS_IPCAG",
                "VALDATA": "2024-02-01T00:00:00-03:00",
                "VALVALOR": 106.2,
                "NIVNOME": "",
                "TERCODIGO": "",
            },
        ]
    }
    macro_file = macro_dir / "PRECOS_IPCAG@20261101.json"
    macro_file.write_text(json.dumps(macro_payload), encoding="utf-8")

    # 3. Regional series values (converted to 'valores_regional')
    reg_payload = {
        "value": [
            {
                "SERCODIGO": "DFEDUCM",
                "VALDATA": "2024-01-01T00:00:00-02:00",
                "VALVALOR": 1500000.0,
                "NIVNOME": "Municípios",
                "TERCODIGO": "3550308",
            }
        ]
    }
    reg_file = reg_dir / "DFEDUCM@20261101.json"
    reg_file.write_text(json.dumps(reg_payload), encoding="utf-8")

    # Run conversion
    res = converter.convert(raw_dir, lake_dir)
    assert res.converted == 3
    assert not res.errors

    lake_ipea = lake_dir / "ipeadata"

    # Verify series (dimension)
    ds_series = lake_ipea / "series"
    errors_series = check_dataset(ds_series)
    assert not errors_series, f"errors in series: {errors_series}"
    (part_series,) = list(ds_series.glob("*.parquet"))
    df_s = pl.read_parquet(part_series)
    assert df_s["sercodigo"][0] == "PRECOS_IPCAG"

    # Verify valores (macro)
    ds_val = lake_ipea / "valores"
    errors_val = check_dataset(ds_val)
    assert not errors_val, f"errors in valores: {errors_val}"
    (part_val,) = list(
        (ds_val / "base=macro" / "periodicidade=mensal").glob("*.parquet")
    )
    df_v = pl.read_parquet(part_val)
    assert df_v.height == 2
    # Verify date slicing without timezone shift
    assert df_v["data"].to_list() == ["2024-01-01", "2024-02-01"]
    assert df_v["valor"].to_list() == [105.5, 106.2]
    assert df_v["nivnome"].to_list() == [None, None]

    # Verify valores_regional
    ds_reg = lake_ipea / "valores_regional"
    errors_reg = check_dataset(ds_reg)
    assert not errors_reg, f"errors in valores_regional: {errors_reg}"
    (part_reg,) = list(
        (ds_reg / "nivel=Municipios" / "periodicidade=mensal").glob("*.parquet")
    )
    df_r = pl.read_parquet(part_reg)
    assert df_r["data"][0] == "2024-01-01"
    assert df_r["valor"][0] == 1500000.0
    assert df_r["tercodigo"][0] == "3550308"
