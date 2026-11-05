"""File location management for ipeadata-fetcher."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from quantilica.core.storage import (
    BaseDataRepository,
    build_stamped_filename,
    stamp_filename,
)


class DataRepository(BaseDataRepository):
    """Manages local storage for ipeadata-fetcher raw files."""

    def __init__(self, root: Path | str) -> None:
        super().__init__(root)

    def path_for_entry(
        self,
        entry: dict[str, Any],
        *,
        last_modified: dt.date | None = None,
    ) -> Path:
        """Compute the local path for a dataset entry."""
        group = entry.get("group", "default")
        ext = entry.get("ext", "csv")
        base_id = entry.get("base_id", entry.get("id", "dataset"))
        year = entry.get("year")
        month = entry.get("month")
        quarter = entry.get("quarter")
        slug = entry.get("slug")

        # ``fixed_stamp`` (AAAAMMDD) vence tudo: caminho estável para recursos
        # sem data de versão. Sem ele, cai na data de hoje quando o servidor
        # não informa uma data confiável.
        fixed = entry.get("fixed_stamp")
        if fixed:
            timestamp = dt.datetime.strptime(str(fixed), "%Y%m%d").date()
        else:
            timestamp = last_modified or dt.date.today()

        if year is None:
            filename = stamp_filename(base_id, ext, timestamp)
        elif month is not None:
            partition = f"{year}-{month:02d}"
            if slug:
                partition = f"{partition}_{slug}"
            filename = build_stamped_filename(
                base_id, partition, ext=ext, timestamp=timestamp
            )
        elif quarter is not None:
            partition = f"{year}-T{quarter:02d}"
            if slug:
                partition = f"{partition}_{slug}"
            filename = build_stamped_filename(
                base_id, partition, ext=ext, timestamp=timestamp
            )
        else:
            partition = str(year)
            if slug:
                partition = f"{partition}_{slug}"
            filename = build_stamped_filename(
                base_id, partition, ext=ext, timestamp=timestamp
            )

        return self.storage.path_for(f"{group}/{filename}")
