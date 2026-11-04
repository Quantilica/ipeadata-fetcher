"""HTTP client for Ipeadata OData v4 API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quantilica.core.http import HostPolicy, HttpClient
from quantilica.core.logging import get_logger
from quantilica.core.manifests import DownloadManifest

from .constants import (
    METADADOS_URL,
    ODATA_BASE_URL,
    ODATA_HOST,
    PAISES_URL,
    TEMAS_URL,
    TERRITORIOS_URL,
    valores_serie_url,
)

logger = get_logger(__name__)


class IpeadataClient:
    """Client for querying Ipeadata OData v4 API."""

    def __init__(
        self,
        *,
        base_url: str = ODATA_BASE_URL,
        client: HttpClient | None = None,
        logger: logging.Logger | None = None,
        workers: int | None = None,
        min_interval: float = 0.25,
        deadline: float | None = 900.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # Com ``workers`` o limite por host (HostPolicy) vale para o pool da carga:
        # no máximo ``workers`` requisições simultâneas, espaçadas de ``min_interval``
        # e abortadas após ``deadline`` segundos.
        policies = (
            {
                ODATA_HOST: HostPolicy(
                    min_interval=min_interval,
                    max_concurrency=max(1, workers),
                    deadline=deadline,
                )
            }
            if workers is not None
            else None
        )
        self.client = client or HttpClient(
            follow_redirects=False,
            http2=False,
            emulate_browser=True,
            host_policies=policies,
        )
        self.logger = logger or get_logger(__name__)

    def _get_odata_values(self, url: str) -> list[dict[str, Any]]:
        """Fetch OData endpoint and unwrap 'value' array."""
        data = self.client.get_json(url)
        if isinstance(data, dict):
            items = data.get("value", [])
            if isinstance(items, list):
                return items
        return []

    def get_metadados(self) -> list[dict[str, Any]]:
        """Fetch all series metadata."""
        return self._get_odata_values(METADADOS_URL)

    def get_temas(self) -> list[dict[str, Any]]:
        """Fetch themes dimension."""
        return self._get_odata_values(TEMAS_URL)

    def get_territorios(self) -> list[dict[str, Any]]:
        """Fetch territories dimension."""
        return self._get_odata_values(TERRITORIOS_URL)

    def get_paises(self) -> list[dict[str, Any]]:
        """Fetch countries dimension."""
        return self._get_odata_values(PAISES_URL)

    def get_valores_serie(self, sercodigo: str) -> list[dict[str, Any]]:
        """Fetch values for a single series by code."""
        url = valores_serie_url(sercodigo)
        return self._get_odata_values(url)

    def download_resource(
        self,
        url: str,
        dest: Path,
        *,
        manifest_path: Path | None = None,
    ) -> DownloadManifest:
        """Download raw JSON endpoint with SHA-256 manifest."""
        # manifest_path is accepted for compatibility but not used by HttpClient
        return self.client.download_with_manifest(
            url,
            dest,
            source_id="ipeadata",
            dataset_id="series",
            producer="ipeadata-fetcher",
        )
