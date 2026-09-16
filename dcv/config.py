"""
DCV configuration.

Secrets come from the environment or docker/.env. Nothing secret is written
into this file, and nothing secret is logged — the SAD's reproducibility
requirement (UC7) means query parameters ARE recorded, but credentials never are.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
DB_PATH = DATA / "dcv.sqlite"

DATA.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)


def _from_env_file(key: str) -> str | None:
    """Read a key from docker/.env without importing a dotenv dependency."""
    env_file = ROOT / "docker" / ".env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def secret(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or _from_env_file(key) or default


# --- Neo4j ------------------------------------------------------------------
# A dedicated instance. See docker/compose.yaml for why it is not the OIRE one.
NEO4J_URI = os.environ.get("DCV_NEO4J_URI", "bolt://127.0.0.1:7787")
NEO4J_USER = os.environ.get("DCV_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = secret("DCV_NEO4J_PASSWORD")

# --- GDELT ------------------------------------------------------------------
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT rejects unauthenticated bursts. Measured on this host: the published
# "one every 5 seconds" is a floor, not the enforced budget — 6s spacing still
# earned a penalty box lasting minutes. 15s is what actually sustains. Requests
# under ~5s return an HTTP 200 carrying a plain-text rate-limit notice rather
# than an error status, so the client must inspect the body, not the code.
GDELT_MIN_INTERVAL_SEC = 15.0
GDELT_MAX_RETRIES = 4

# Verified empirically 2026-09-15 against the live API:
#   2017-01-01  accepted
#   2015-01-01  rejected — "Invalid query start date."
#   2014-04-01  rejected — "Invalid query start date."
# The DOC 2.0 article index does not reach 2014. This contradicts the SAD's
# data-source table and is recorded here so the constraint cannot be lost.
GDELT_DOC_EARLIEST = "2017-01-01"

# --- Inference --------------------------------------------------------------
# SAD Open Item 3. DeepSeek is named in the SAD as existing on this host; it is
# not configured here. Local Ollama is present and is the working fallback.
# Model identity is recorded on every extraction for reproducibility (UC-N1).
OLLAMA_URL = os.environ.get("DCV_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("DCV_OLLAMA_MODEL", "qwen3:8b-q4_K_M")
OLLAMA_NUM_THREAD = int(os.environ.get("DCV_OLLAMA_NUM_THREAD", "4"))
DEEPSEEK_API_KEY = secret("DEEPSEEK_API_KEY")

# --- Ground-truth sources ---------------------------------------------------
# Both require credentials. The SAD lists ACLED as "REST, OAuth" and UCDP as
# "REST, versioned" without noting that UCDP is also authenticated.
#
# Verified 2026-09-15:
#   api.acleddata.com        does not resolve — the host in the SAD is dead.
#   acleddata.com/api/...    live, behind a Cloudflare challenge.
#   ucdp gedevents/24.1|25.1 HTTP 401 "API token required.
#                            Add header: x-ucdp-access-token: <your-token>"
ACLED_API = "https://acleddata.com/api/acled/read"
ACLED_KEY = secret("ACLED_KEY")
ACLED_EMAIL = secret("ACLED_EMAIL")

UCDP_GED_API = "https://ucdpapi.pcr.uu.se/api/gedevents"
UCDP_VERSION = os.environ.get("DCV_UCDP_VERSION", "25.1")
UCDP_TOKEN = secret("UCDP_TOKEN")
UCDP_AUTH_HEADER = "x-ucdp-access-token"
