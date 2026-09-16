"""
GDELT DOC 2.0 client (UC2).

Two behaviours of this API drive the design and are worth stating, because
neither is discoverable from the documentation:

1. Rate limiting returns HTTP 200 with a plain-text notice in the body, not a
   429 and not JSON. Code that checks the status and then calls .json() will
   crash on a condition that is merely "wait five seconds". The client must
   inspect the body.

2. The article index does not reach 2014. Verified 2026-09-15: a 2017 start
   date is accepted, 2015 and 2014 return "Invalid query start date." The SAD's
   data-source table records GDELT DOC 2.0 as "2014+ confirmed"; it is not.
   A pull below GDELT_DOC_EARLIEST is refused here rather than allowed to
   produce a silently empty series that would look like "no coverage".
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Any

import requests

from . import store
from .config import (GDELT_DOC_API, GDELT_DOC_EARLIEST, GDELT_MAX_RETRIES,
                     GDELT_MIN_INTERVAL_SEC, LOGS)

# Throttle state is persisted, not held in a module global. Two consecutive CLI
# invocations are two processes; an in-memory interval would let the second one
# fire immediately and earn a longer penalty than the limit it was avoiding.
_STAMP = LOGS / ".gdelt_last_call"


class GdeltWindowUnavailable(RuntimeError):
    """The requested window predates the DOC 2.0 index."""


def _throttle() -> None:
    try:
        last = float(_STAMP.read_text())
    except (OSError, ValueError):
        last = 0.0
    wait = GDELT_MIN_INTERVAL_SEC - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    try:
        _STAMP.write_text(str(time.time()))
    except OSError:
        pass   # throttling is best-effort; never block a pull on a write failure


def _is_rate_limit(body: str) -> bool:
    low = body[:400].lower()
    return "limit requests" in low or "high-traffic" in low


def _stamp(d: str, end: bool = False) -> str:
    """'2020-10-01' -> '20201001000000' (GDELT's compact form)."""
    dt = datetime.strptime(d, "%Y-%m-%d")
    return dt.strftime("%Y%m%d") + ("235959" if end else "000000")


def check_window(start: str) -> None:
    if start < GDELT_DOC_EARLIEST:
        raise GdeltWindowUnavailable(
            f"GDELT DOC 2.0 indexes from {GDELT_DOC_EARLIEST}; requested start {start}. "
            "The 2014 narrative layer is not reachable through this API — see README."
        )


def fetch(case_id: int, *, query: str, mode: str, start: str, end: str,
          maxrecords: int | None = None) -> tuple[list[dict[str, Any]], int]:
    """One GDELT call, fully provenanced. Returns (rows, pull_id)."""
    check_window(start)

    params: dict[str, Any] = {
        "query": query,
        "mode": mode,
        "startdatetime": _stamp(start),
        "enddatetime": _stamp(end, end=True),
        "format": "json",
    }
    if maxrecords:
        params["maxrecords"] = maxrecords

    pull_id = store.open_pull(case_id, "gdelt_doc", GDELT_DOC_API, params)

    body, status = "", None
    for attempt in range(1, GDELT_MAX_RETRIES + 1):
        _throttle()
        try:
            resp = requests.get(GDELT_DOC_API, params=params, timeout=60)
        except requests.RequestException as exc:
            store.close_pull(pull_id, outcome="error", error=str(exc)[:400])
            raise

        status, body = resp.status_code, resp.text
        if _is_rate_limit(body):
            # Back off progressively; the published limit is a floor, not a promise.
            time.sleep(GDELT_MIN_INTERVAL_SEC * attempt)
            continue
        break
    else:
        store.close_pull(pull_id, outcome="rate_limited", status=status,
                         error="rate limited after retries")
        raise RuntimeError("GDELT rate limit persisted across retries")

    if body.strip().lower().startswith("invalid"):
        store.close_pull(pull_id, outcome="rejected", status=status, error=body.strip()[:400])
        raise GdeltWindowUnavailable(body.strip())

    sha = hashlib.sha256(body.encode()).hexdigest()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        store.close_pull(pull_id, outcome="error", status=status,
                         sha256=sha, error=body.strip()[:400])
        raise RuntimeError(f"GDELT returned non-JSON: {body.strip()[:160]}")

    rows = _normalise(payload, mode, params)
    store.close_pull(pull_id, outcome="success" if rows else "empty",
                     status=status, count=len(rows), sha256=sha)
    return rows, pull_id


def _normalise(payload: dict, mode: str, params: dict) -> list[dict[str, Any]]:
    """Map a GDELT response into the SAD Section 8 shared record schema."""
    retrieved = store.now()
    method = f"GET {GDELT_DOC_API} {json.dumps(params, sort_keys=True)}"
    out: list[dict[str, Any]] = []

    if mode in ("timelinevol", "timelinetone"):
        for series in payload.get("timeline", []):
            label = series.get("series", mode)
            for point in series.get("data", []):
                raw_date = str(point.get("date", ""))
                iso = (f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                       if len(raw_date) >= 8 else None)
                out.append({
                    "source_platform": "gdelt_doc",
                    "source_record_id": f"{mode}:{label}:{raw_date}",
                    "event_date": iso,
                    "event_type": f"{mode}:{label}",
                    "tone_score": float(point["value"]) if mode == "timelinetone" else None,
                    "content_summary": None,
                    "location": None,
                    "fatalities": None,
                    "language": None,
                    "retrieval_method": method,
                    "retrieved_at": retrieved,
                    "raw_json": json.dumps({"series": label, **point}, sort_keys=True),
                    # value carried for timelinevol so volume is not lost
                    "_value": point.get("value"),
                })
        # timelinevol has no tone; keep the volume in raw_json and event_type.
        for row in out:
            row.pop("_value", None)

    elif mode == "artlist":
        for art in payload.get("articles", []):
            d = str(art.get("seendate", ""))
            iso = f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else None
            out.append({
                "source_platform": "gdelt_doc",
                "source_record_id": art.get("url"),
                "event_date": iso,
                "event_type": "article",
                "location": art.get("sourcecountry"),
                "content_summary": art.get("title"),
                "tone_score": None,
                "fatalities": None,
                "language": art.get("language"),
                "retrieval_method": method,
                "retrieved_at": retrieved,
                "raw_json": json.dumps(art, sort_keys=True),
            })

    return out
