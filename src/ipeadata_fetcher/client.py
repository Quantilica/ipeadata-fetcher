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
        # Otimização: desabilita HEAD (endpoint OData não suporta → 404)
        # Aumenta attempts/timeout para GETs lentos do OData
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
            attempts=5,
            timeout=120.0,
            retry_base_delay=1.0,
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
        force: bool = False,
    ) -> DownloadManifest:
        """Download raw JSON endpoint with SHA-256 manifest.

        Bypasses HEAD freshness check (Ipeadata OData returns 404 on HEAD).
        Uses GET streaming to capture headers for manifest.
        """
        import hashlib

        from quantilica.core.files import ensure_parent, write_stream_atomic
        from quantilica.core.http import DownloadManifest
        from quantilica.core.manifests import write_manifest_sidecar

        target = Path(dest)
        ensure_parent(target)

        # Direct GET streaming - bypass HEAD freshness check entirely
        # Ipeadata OData returns 404 on HEAD, but GET works
        sha256 = hashlib.sha256()
        size_bytes = 0
        response_headers = {}

        def _stream(cb):
            nonlocal size_bytes, response_headers
            with self.client.stream("GET", url) as response:
                response.raise_for_status()
                # Capture headers from the streaming GET response
                response_headers["Last-Modified"] = response.headers.get(
                    "Last-Modified"
                )
                response_headers["ETag"] = response.headers.get("ETag")
                response_headers["Content-Length"] = response.headers.get(
                    "Content-Length"
                )
                for chunk in response.iter_bytes():
                    sha256.update(chunk)
                    size_bytes += len(chunk)
                    cb(chunk)

        write_stream_atomic(
            dest,
            lambda w: _stream(w),
            validate=lambda p: None,  # JSON payload validation happens in backfill
        )

        manifest = DownloadManifest.from_digest(
            source_id="ipeadata",
            dataset_id="series",
            url=url,
            sha256=sha256.hexdigest(),
            size_bytes=size_bytes,
            path=str(target.absolute()),
            producer="ipeadata-fetcher",
            metadata={
                "remote_last_modified": response_headers.get("Last-Modified"),
                "remote_etag": response_headers.get("ETag"),
                "remote_content_length": response_headers.get("Content-Length"),
            },
        )
        write_manifest_sidecar(target, manifest)
        return target
