"""
Ground-truth event ingestion: ACLED and UCDP GED (UC3, UC-N2).

Both are the *verification* layer. GDELT tells us what was said; these tell us
what was coded to have happened. UC-N2 matches extracted claims against them,
and Ts depends on the comparison.

Two verified deviations from the SAD, both found 2026-09-15:

1. **ACLED moved.** `api.acleddata.com` no longer resolves. The live base is
   `https://acleddata.com/api/`, and auth is OAuth2 *password grant* against
   `https://acleddata.com/oauth/token` — not a bare API key. Access tokens live
   24h, refresh tokens 14 days.

2. **Cloudflare challenges this host.** Every path on acleddata.com returns
   HTTP 403 with `cf-mitigated: challenge` from 169.58.84.78, including the
   public homepage. This is an edge decision about the IP, not about the
   account, so no credential and no User-Agent clears it. Hence `import_file()`:
   download on a machine that clears the challenge, load here, keep provenance.
   Either path lands in the same `records` rows with the same §8 fields.

UCDP needs a token too, which the SAD does not mention — `x-ucdp-access-token`,
requested at ucdp.uu.se/apidocs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import time
from pathlib import Path
from typing import Any, Iterator

import requests

from . import config, parameters, store

ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_CLIENT_ID = "acled"
TOKEN_CACHE = config.LOGS / ".acled_token.json"

# Refresh this far before nominal expiry, so a long pull cannot expire mid-run.
TOKEN_SKEW_SEC = 600


class GroundTruthError(RuntimeError):
    pass


class EdgeChallenged(GroundTruthError):
    """Cloudflare blocked the request before it reached ACLED's application."""


# --------------------------------------------------------------------------
# ACLED OAuth
# --------------------------------------------------------------------------

def _load_cached_token() -> dict[str, Any] | None:
    try:
        data = json.loads(TOKEN_CACHE.read_text())
    except (OSError, ValueError):
        return None
    if data.get("expires_at", 0) - TOKEN_SKEW_SEC > time.time():
        return data
    return data if data.get("refresh_token") else None


def _save_token(payload: dict[str, Any]) -> dict[str, Any]:
    data = {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "expires_at": time.time() + int(payload.get("expires_in", 86400)),
    }
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps(data))
    os.chmod(TOKEN_CACHE, 0o600)          # it is a credential; treat it as one
    return data


def _token_request(form: dict[str, str]) -> dict[str, Any]:
    resp = requests.post(ACLED_TOKEN_URL, data=form, timeout=60,
                         headers={"Accept": "application/json"})
    if resp.status_code == 403 and "challenge" in resp.headers.get("cf-mitigated", ""):
        raise EdgeChallenged(
            "Cloudflare challenged this host before ACLED saw the request "
            f"(cf-ray {resp.headers.get('cf-ray')}). Credentials are not the "
            "problem. Use import_file(), or ask ACLED to allowlist this IP."
        )
    if resp.status_code != 200:
        raise GroundTruthError(f"ACLED token HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def acled_token(force: bool = False) -> str:
    """
    Access token, from cache / refresh / password grant in that order.

    Note on account setup: the password grant needs a myACLED *password*. An
    account created purely through Google sign-in has none until one is set, and
    the grant then fails with invalid_grant on credentials that look correct.
    """
    cached = None if force else _load_cached_token()
    if cached and cached.get("expires_at", 0) - TOKEN_SKEW_SEC > time.time():
        return cached["access_token"]

    if cached and cached.get("refresh_token"):
        try:
            return _save_token(_token_request({
                "refresh_token": cached["refresh_token"],
                "grant_type": "refresh_token",
                "client_id": ACLED_CLIENT_ID,
            }))["access_token"]
        except GroundTruthError:
            pass                            # fall through to a full grant

    email = config.ACLED_EMAIL
    password = config.secret("ACLED_PASSWORD")
    if not email or not password:
        raise GroundTruthError(
            "ACLED_EMAIL and ACLED_PASSWORD must be set in docker/.env. "
            "The current API uses an OAuth password grant, not the bare access "
            "key the SAD describes."
        )
    return _save_token(_token_request({
        "username": email, "password": password,
        "grant_type": "password", "client_id": ACLED_CLIENT_ID,
        "scope": "authenticated",
    }))["access_token"]


# --------------------------------------------------------------------------
# Normalisation — SAD §8, shared with the GDELT paths
# --------------------------------------------------------------------------

def _incident_type_for(platform: str, event_type: str, violence_type: Any) -> str | None:
    """
    Map a coded event back onto the approved taxonomy (Open Item 5).

    Returns None when the event falls outside all five types — recorded rather
    than forced, because a silent misassignment corrupts UC-N2 matching.
    """
    for name, spec in parameters.INCIDENT_TYPES.items():
        if platform == "acled" and event_type in spec["acled_event_types"]:
            return name
        if platform == "ucdp_ged":
            try:
                if int(violence_type) in spec["ucdp_type_of_violence"]:
                    return name
            except (TypeError, ValueError):
                pass
    return None


def _acled_row(row: dict[str, Any], method: str, retrieved: str) -> dict[str, Any]:
    etype = (row.get("event_type") or "").strip()
    loc = "; ".join(filter(None, [row.get("location"), row.get("admin1"),
                                  row.get("country")]))
    try:
        fatalities = int(row.get("fatalities") or 0)
    except (TypeError, ValueError):
        fatalities = None
    return {
        "source_platform": "acled",
        "source_record_id": row.get("event_id_cnty"),
        "event_date": row.get("event_date"),
        "event_type": etype,
        "location": loc[:255] or None,
        # ACLED notes are the coded narrative — the text UC-N2 compares against.
        "content_summary": (row.get("notes") or "")[:2000] or None,
        "tone_score": None,
        "fatalities": fatalities,
        "language": None,
        "retrieval_method": method,
        "retrieved_at": retrieved,
        "raw_json": json.dumps({
            "sub_event_type": row.get("sub_event_type"),
            "disorder_type": row.get("disorder_type"),
            "actor1": row.get("actor1"), "actor2": row.get("actor2"),
            "assoc_actor_1": row.get("assoc_actor_1"),
            "assoc_actor_2": row.get("assoc_actor_2"),
            "latitude": row.get("latitude"), "longitude": row.get("longitude"),
            "geo_precision": row.get("geo_precision"),
            "time_precision": row.get("time_precision"),
            "source": row.get("source"), "source_scale": row.get("source_scale"),
            "civilian_targeting": row.get("civilian_targeting"),
            "tags": row.get("tags"),
            "incident_type": _incident_type_for("acled", etype, None),
        }, sort_keys=True),
    }


def _ucdp_row(row: dict[str, Any], method: str, retrieved: str) -> dict[str, Any]:
    vtype = row.get("type_of_violence")
    loc = "; ".join(filter(None, [row.get("where_coordinates"),
                                  row.get("adm_1"), row.get("country")]))
    return {
        "source_platform": "ucdp_ged",
        "source_record_id": str(row.get("id")),
        "event_date": (row.get("date_start") or "")[:10] or None,
        "event_type": f"ucdp_violence_{vtype}",
        "location": loc[:255] or None,
        "content_summary": (row.get("source_article") or "")[:2000] or None,
        "tone_score": None,
        "fatalities": row.get("best"),
        "language": None,
        "retrieval_method": method,
        "retrieved_at": retrieved,
        "raw_json": json.dumps({
            "conflict_name": row.get("conflict_name"),
            "side_a": row.get("side_a"), "side_b": row.get("side_b"),
            "date_end": row.get("date_end"),
            "deaths_a": row.get("deaths_a"), "deaths_b": row.get("deaths_b"),
            "deaths_civilians": row.get("deaths_civilians"),
            "deaths_unknown": row.get("deaths_unknown"),
            "low": row.get("low"), "high": row.get("high"),
            "where_prec": row.get("where_prec"), "date_prec": row.get("date_prec"),
            "latitude": row.get("latitude"), "longitude": row.get("longitude"),
            "type_of_violence": vtype,
            "incident_type": _incident_type_for("ucdp_ged", "", vtype),
        }, sort_keys=True),
    }


# --------------------------------------------------------------------------
# ACLED fetch — live API
# --------------------------------------------------------------------------

def fetch_acled(case_id: int, country: str, start: str, end: str,
                limit: int = 5000) -> int:
    """One ACLED window into `records`. Raises EdgeChallenged if Cloudflare blocks."""
    params = {
        "_format": "json", "country": country,
        "event_date": f"{start}|{end}", "event_date_where": "BETWEEN",
        "limit": limit,
    }
    pull_id = store.open_pull(case_id, "acled", config.ACLED_API, params)
    try:
        token = acled_token()
        resp = requests.get(config.ACLED_API, params=params, timeout=180,
                            headers={"Authorization": f"Bearer {token}",
                                     "Accept": "application/json"})
    except EdgeChallenged as exc:
        store.close_pull(pull_id, outcome="rejected", status=403, error=str(exc)[:400])
        raise
    except Exception as exc:                        # noqa: BLE001
        store.close_pull(pull_id, outcome="error", error=str(exc)[:400])
        raise

    if resp.status_code == 403 and "challenge" in resp.headers.get("cf-mitigated", ""):
        store.close_pull(pull_id, outcome="rejected", status=403,
                         error="cloudflare challenge")
        raise EdgeChallenged("Cloudflare challenged the data request.")
    if resp.status_code != 200:
        store.close_pull(pull_id, outcome="rejected", status=resp.status_code,
                         error=resp.text[:400])
        raise GroundTruthError(f"ACLED HTTP {resp.status_code}: {resp.text[:300]}")

    payload = resp.json()
    data = payload.get("data", [])
    retrieved = store.now()
    method = f"GET {config.ACLED_API} {json.dumps(params, sort_keys=True)}"
    rows = [{**_acled_row(r, method, retrieved), "case_id": case_id,
             "pull_id": pull_id} for r in data]
    store.insert_records(rows)
    store.close_pull(pull_id, outcome="success" if rows else "empty",
                     status=200, count=len(rows),
                     sha256=hashlib.sha256(resp.content).hexdigest())
    if len(data) >= limit:
        print(f"    WARNING: {len(data)} rows == limit; window is truncated. "
              f"Narrow the range or paginate.")
    return len(rows)


# --------------------------------------------------------------------------
# ACLED fetch — file import, for when the edge blocks this host
# --------------------------------------------------------------------------

def import_file(case_id: int, path: str, platform: str = "acled") -> int:
    """
    Load an ACLED CSV/JSON export downloaded elsewhere.

    Provenance is weaker than an API pull and is recorded honestly as such: the
    `pulls` row carries the local path, the file's SHA-256 and the marker
    `manual_export`, so UC7 can still trace any figure to a byte-identical file
    even though this host did not make the request itself.
    """
    p = Path(path)
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    params = {"mode": "manual_export", "path": str(p.resolve()),
              "bytes": len(raw), "sha256": digest}
    pull_id = store.open_pull(case_id, platform, f"file://{p.resolve()}", params)

    try:
        text = raw.decode("utf-8", errors="replace")
        if p.suffix.lower() == ".json" or text.lstrip().startswith(("{", "[")):
            doc = json.loads(text)
            data = doc.get("data", doc) if isinstance(doc, dict) else doc
        else:
            data = list(csv.DictReader(io.StringIO(text)))
    except Exception as exc:                        # noqa: BLE001
        store.close_pull(pull_id, outcome="error", error=str(exc)[:400])
        raise

    retrieved = store.now()
    method = f"manual export sha256:{digest[:16]} loaded from {p.name}"
    norm = _acled_row if platform == "acled" else _ucdp_row
    rows = [{**norm(r, method, retrieved), "case_id": case_id,
             "pull_id": pull_id} for r in data]
    store.insert_records(rows)
    store.close_pull(pull_id, outcome="success" if rows else "empty",
                     count=len(rows), sha256=digest)
    return len(rows)


# --------------------------------------------------------------------------
# UCDP GED
# --------------------------------------------------------------------------

def fetch_ucdp(case_id: int, country_id: int, start_year: int, end_year: int,
               page_size: int = 1000) -> int:
    """
    UCDP GED for a country/year range, following NextPageUrl to exhaustion.

    Note the coverage limit this imposes on the design: GED only codes events
    reaching its fatality threshold, and codes no protest at all. For the
    #EndSARS case UCDP is expected to return little or nothing — that is the
    dataset behaving correctly, not a pull failure, and Open Item 7 has to
    account for it.
    """
    if not config.UCDP_TOKEN:
        raise GroundTruthError(
            "UCDP_TOKEN missing. GED now requires the header "
            f"'{config.UCDP_AUTH_HEADER}'; request one at ucdp.uu.se/apidocs."
        )
    base = f"{config.UCDP_GED_API}/{config.UCDP_VERSION}"
    params: dict[str, Any] = {"pagesize": page_size, "Country": country_id,
                              "StartDate": f"{start_year}-01-01",
                              "EndDate": f"{end_year}-12-31"}
    pull_id = store.open_pull(case_id, "ucdp_ged", base, params)
    headers = {config.UCDP_AUTH_HEADER: config.UCDP_TOKEN,
               "Accept": "application/json"}

    total, url, hasher = 0, base, hashlib.sha256()
    retrieved = store.now()
    try:
        while url:
            resp = requests.get(url, params=params if url == base else None,
                                headers=headers, timeout=180)
            if resp.status_code != 200:
                store.close_pull(pull_id, outcome="rejected",
                                 status=resp.status_code, error=resp.text[:400])
                raise GroundTruthError(f"UCDP HTTP {resp.status_code}: {resp.text[:300]}")
            hasher.update(resp.content)
            doc = resp.json()
            batch = doc.get("Result", [])
            method = f"GET {base} {json.dumps(params, sort_keys=True)}"
            store.insert_records([
                {**_ucdp_row(r, method, retrieved), "case_id": case_id,
                 "pull_id": pull_id} for r in batch])
            total += len(batch)
            url = doc.get("NextPageUrl") or None
    except GroundTruthError:
        raise
    except Exception as exc:                        # noqa: BLE001
        store.close_pull(pull_id, outcome="error", error=str(exc)[:400])
        raise

    store.close_pull(pull_id, outcome="success" if total else "empty", status=200,
                     count=total, sha256=hasher.hexdigest())
    return total
