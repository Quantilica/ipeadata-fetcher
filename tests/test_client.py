"""Tests for IpeadataClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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

    # Mock the streaming GET and head_or_get calls
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = [b"test content"]
    mock_response.headers = {
        "Last-Modified": "Mon, 01 Jan 2024 12:00:00 GMT",
        "ETag": "abc123",
        "Content-Length": "12",
    }

    mock_stream_cm = MagicMock()
    mock_stream_cm.__enter__ = MagicMock(return_value=mock_response)
    mock_stream_cm.__exit__ = MagicMock(return_value=False)

    with patch.object(
        client.client, "stream", return_value=mock_stream_cm
    ) as mock_stream:
        with patch.object(client.client, "head_or_get", return_value=mock_response):
            res = client.download_resource("https://ipeadata/test.json", target)
            assert res == target
            assert res.exists()
            mock_stream.assert_called_once()
