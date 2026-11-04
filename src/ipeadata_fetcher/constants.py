"""Constants and endpoint definitions for ipeadata-fetcher."""

from __future__ import annotations

ODATA_HOST = "www.ipeadata.gov.br"
ODATA_BASE_URL = f"https://{ODATA_HOST}/api/odata4"
METADADOS_URL = f"{ODATA_BASE_URL}/Metadados"
TEMAS_URL = f"{ODATA_BASE_URL}/Temas"
TERRITORIOS_URL = f"{ODATA_BASE_URL}/Territorios"
PAISES_URL = f"{ODATA_BASE_URL}/Paises"


def valores_serie_url(sercodigo: str) -> str:
    """Generate OData function URL for ValoresSerie."""
    escaped = sercodigo.replace("'", "''")
    return f"{ODATA_BASE_URL}/ValoresSerie(SERCODIGO='{escaped}')"


# Macro-bases in Ipeadata
BASES: dict[str, str] = {
    "macro": "Macroeconômico",
    "social": "Social",
    "regional": "Regional",
}
