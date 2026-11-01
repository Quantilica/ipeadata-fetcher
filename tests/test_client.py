"""Tests for IpeadataClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from quantilica.core.manifests import DownloadManifest

from ipeadata_fetcher.client import IpeadataClient


def test_client_init() -> None:
    client = IpeadataClient()
    assert client.base_url == "https://www.ipeadata.gov.br/api/odata4"


def test_get_metadados() -> None:
    client = IpeadataClient()
    fake_payload = {"value": [{"SERCODIGO": "PRECOS_IPCAG", "SERNOME": "IPCA Geral"}]}
    with patch.object(client.client, "get_json", return_value=fake_payload):
        res = client.get_metadados()
        assert len(res) == 1
        assert res[0]["SERCODIGO"] == "PRECOS_IPCAG"


def test_get_valores_serie() -> None:
    client = IpeadataClient()
    fake_payload = {
        "value": [
            {
                "SERCODIGO": "PRECOS_IPCAG",
                "VALDATA": "2024-01-01T00:00:00-02:00",
                "VALVALOR": 105.5,
            }
        ]
    }
    with patch.object(client.client, "get_json", return_value=fake_payload):
        res = client.get_valores_serie("PRECOS_IPCAG")
        assert len(res) == 1
        assert res[0]["VALVALOR"] == 105.5


def test_download_resource(tmp_path) -> None:
    client = IpeadataClient()
    target = tmp_path / "test.json"
    mock_manifest = MagicMock(spec=DownloadManifest)
    with patch.object(
        client.client, "download_with_manifest", return_value=mock_manifest
    ):
        res = client.download_resource("https://ipeadata/test.json", target)
        assert res == mock_manifest
