"""Tests for ipeadata-fetcher storage module."""

import datetime as dt

from ipeadata_fetcher.storage import DataRepository


def test_path_for_entry_fallback_timestamp() -> None:
    """When last_modified is None, filename gets today's @YYYYMMDD timestamp."""
    repo = DataRepository("/tmp/test")
    entry = {
        "id": "SERIE_TEST",
        "base_id": "SERIE_TEST",
        "group": "macro",
        "ext": "json",
        "slug": "SERIE_TEST",
    }

    path = repo.path_for_entry(entry, last_modified=None)

    today = dt.date.today().strftime("%Y%m%d")
    assert f"@{today}" in path.name
    assert path.name.startswith("SERIE_TEST@")
    assert path.name.endswith(".json")


def test_path_for_entry_with_last_modified() -> None:
    """When last_modified is provided, filename uses that date."""
    repo = DataRepository("/tmp/test")
    entry = {
        "id": "SERIE_TEST",
        "base_id": "SERIE_TEST",
        "group": "macro",
        "ext": "json",
        "slug": "SERIE_TEST",
    }

    test_date = dt.date(2024, 3, 15)
    path = repo.path_for_entry(entry, last_modified=test_date)

    assert "@20240315" in path.name
    assert path.name.startswith("SERIE_TEST@")
    assert path.name.endswith(".json")


def test_path_for_entry_with_year_partition() -> None:
    """Year partition is included in filename when year is present."""
    repo = DataRepository("/tmp/test")
    entry = {
        "id": "SERIE_TEST",
        "base_id": "SERIE_TEST",
        "group": "macro",
        "ext": "json",
        "slug": "SERIE_TEST",
        "year": 2024,
    }

    test_date = dt.date(2024, 3, 15)
    path = repo.path_for_entry(entry, last_modified=test_date)

    assert "2024" in path.name
    assert "@20240315" in path.name
    assert path.name.endswith(".json")


def test_path_for_entry_with_year_month_partition() -> None:
    """Year-month partition is included in filename when year and month are present."""
    repo = DataRepository("/tmp/test")
    entry = {
        "id": "SERIE_TEST",
        "base_id": "SERIE_TEST",
        "group": "macro",
        "ext": "json",
        "slug": "SERIE_TEST",
        "year": 2024,
        "month": 3,
    }

    test_date = dt.date(2024, 3, 15)
    path = repo.path_for_entry(entry, last_modified=test_date)

    assert "2024-03" in path.name
    assert "@20240315" in path.name
    assert path.name.endswith(".json")


def test_path_for_entry_with_year_quarter_partition() -> None:
    """Year-quarter partition appears in the filename when both are set."""
    repo = DataRepository("/tmp/test")
    entry = {
        "id": "SERIE_TEST",
        "base_id": "SERIE_TEST",
        "group": "macro",
        "ext": "json",
        "slug": "SERIE_TEST",
        "year": 2024,
        "quarter": 1,
    }

    test_date = dt.date(2024, 3, 15)
    path = repo.path_for_entry(entry, last_modified=test_date)

    assert "2024-T01" in path.name
    assert "@20240315" in path.name
    assert path.name.endswith(".json")


def test_path_for_entry_with_slug_in_partition() -> None:
    """Slug is appended to partition when present."""
    repo = DataRepository("/tmp/test")
    entry = {
        "id": "SERIE_TEST",
        "base_id": "SERIE_TEST",
        "group": "macro",
        "ext": "json",
        "slug": "custom-slug",
        "year": 2024,
        "month": 3,
    }

    test_date = dt.date(2024, 3, 15)
    path = repo.path_for_entry(entry, last_modified=test_date)

    assert "2024-03_custom-slug" in path.name
    assert "@20240315" in path.name
    assert path.name.endswith(".json")


def test_path_for_entry_default_group() -> None:
    """Default group is used when not specified."""
    repo = DataRepository("/tmp/test")
    entry = {
        "id": "SERIE_TEST",
        "base_id": "SERIE_TEST",
        "ext": "json",
    }

    path = repo.path_for_entry(entry, last_modified=dt.date(2024, 3, 15))

    assert path.parts[-2] == "default"
    assert "@20240315" in path.name


def test_path_for_entry_default_ext() -> None:
    """Default extension is csv when not specified."""
    repo = DataRepository("/tmp/test")
    entry = {
        "id": "SERIE_TEST",
        "base_id": "SERIE_TEST",
        "group": "macro",
    }

    path = repo.path_for_entry(entry, last_modified=dt.date(2024, 3, 15))

    assert path.name.endswith(".csv")
    assert "@20240315" in path.name
