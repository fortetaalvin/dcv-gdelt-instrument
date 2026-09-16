"""
GDELT GKG v1 ingestion (UC2, pre-2017 path).

Why this exists: the DOC 2.0 API rejects any start date before 2017, so the
Chibok 2014 case has no narrative layer through it. The v1 GKG archive reaches
April 2013 as daily files at data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip and
restores that coverage.

Format verified against the 2014-04-14 file: 11 tab-delimited columns, no
quoting, ~59k rows/day, 17 MB compressed to 51 MB raw.

    DATE NUMARTS COUNTS THEMES LOCATIONS PERSONS ORGANIZATIONS TONE
    CAMEOEVENTIDS SOURCES SOURCEURLS

Two things differ materially from DOC 2.0 and shape the design:

1. GKG carries no article text — only extracted themes, entities, counts and
   tone, plus source URLs. UC-N1 as written ("given raw GDELT article/GKG
   content") therefore has structured fields to work from here, not prose. If
   full text is needed for 2014, it has to be fetched from SOURCEURLS, which is
   a separate decision with its own reliability problems (link rot at ten years).

2. A day is 51 MB raw and the Chibok window is ~243 days — roughly 12 GB if
   stored whole. Rows are filtered at parse time against the case's location
   terms and only matches are retained.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from datetime import date, datetime, timedelta
from typing import Any, Iterator

import requests

from . import store

GKG_V1_BASE = "http://data.gdeltproject.org/gkg"
GKG_V1_EARLIEST = "2013-04-01"

COLUMNS = ["DATE", "NUMARTS", "COUNTS", "THEMES", "LOCATIONS", "PERSONS",
           "ORGANIZATIONS", "TONE", "CAMEOEVENTIDS", "SOURCES", "SOURCEURLS"]

csv.field_size_limit(sys.maxsize)


class GkgUnavailable(RuntimeError):
    pass


def _day_url(d: date) -> str:
    return f"{GKG_V1_BASE}/{d.strftime('%Y%m%d')}.gkg.csv.zip"


def daterange(start: str, end: str) -> Iterator[date]:
    a = datetime.strptime(start, "%Y-%m-%d").date()
    b = datetime.strptime(end, "%Y-%m-%d").date()
    while a <= b:
        yield a
        a += timedelta(days=1)


def _parse_tone(raw: str) -> dict[str, float]:
    """TONE is 6 comma-separated floats; only the first is the tone proper."""
    parts = (raw or "").split(",")
    keys = ("tone", "positive", "negative", "polarity", "activity_density", "self_density")
    out: dict[str, float] = {}
    for key, val in zip(keys, parts):
        try:
            out[key] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _matches(row: dict[str, str], terms: list[str]) -> bool:
    """Case-insensitive match across the fields that carry meaning for us."""
    hay = " ".join((row.get(f) or "") for f in
                   ("THEMES", "LOCATIONS", "PERSONS", "ORGANIZATIONS", "SOURCEURLS")).lower()
    return any(t.lower() in hay for t in terms)


def fetch_day(case_id: int, day: date, terms: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Download one GKG day, keep only rows matching `terms`, normalise to §8."""
    url = _day_url(day)
    params = {"date": day.isoformat(), "terms": sorted(terms)}
    pull_id = store.open_pull(case_id, "gdelt_gkg", url, params)

    try:
        resp = requests.get(url, timeout=180, allow_redirects=True)
    except requests.RequestException as exc:
        store.close_pull(pull_id, outcome="error", error=str(exc)[:400])
        raise

    if resp.status_code != 200:
        store.close_pull(pull_id, outcome="rejected", status=resp.status_code,
                         error=f"no GKG file for {day.isoformat()}")
        raise GkgUnavailable(f"GKG v1 has no file for {day.isoformat()} (HTTP {resp.status_code})")

    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        name = zf.namelist()[0]
        text = zf.read(name).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, IndexError) as exc:
        store.close_pull(pull_id, outcome="error", status=200, error=str(exc)[:200])
        raise

    rows: list[dict[str, Any]] = []
    retrieved = store.now()
    method = f"GET {url} (filtered on {sorted(terms)})"
    scanned = 0

    reader = csv.DictReader(io.StringIO(text), delimiter="\t", fieldnames=COLUMNS)
    first = True
    for rec in reader:
        if first:                      # the file carries a header line
            first = False
            if (rec.get("DATE") or "").upper() == "DATE":
                continue
        scanned += 1
        if not _matches(rec, terms):
            continue
        tone = _parse_tone(rec.get("TONE", ""))
        urls = (rec.get("SOURCEURLS") or "").split("<UDIV>")
        rows.append({
            "source_platform": "gdelt_gkg",
            "source_record_id": f"gkg1:{day.isoformat()}:{scanned}",
            "event_date": day.isoformat(),
            "event_type": "gkg_record",
            "location": (rec.get("LOCATIONS") or "")[:255] or None,
            "content_summary": (rec.get("THEMES") or "")[:2000] or None,
            "tone_score": tone.get("tone"),
            "fatalities": None,
            "language": None,
            "retrieval_method": method,
            "retrieved_at": retrieved,
            "raw_json": json.dumps({
                "numarts": rec.get("NUMARTS"),
                "themes": (rec.get("THEMES") or "").split(";")[:60],
                "persons": (rec.get("PERSONS") or "").split(";")[:40],
                "organizations": (rec.get("ORGANIZATIONS") or "").split(";")[:40],
                "locations": (rec.get("LOCATIONS") or "").split(";")[:40],
                "tone": tone,
                "sourceurls": urls[:10],
            }, sort_keys=True),
        })

    store.close_pull(pull_id, outcome="success" if rows else "empty",
                     status=200, count=len(rows))
    return rows, pull_id


def ingest_window(case_id: int, start: str, end: str, terms: list[str],
                  progress: bool = True) -> dict[str, int]:
    """Ingest a date range. Skips days already pulled for this case."""
    if start < GKG_V1_EARLIEST:
        raise GkgUnavailable(f"GKG v1 begins {GKG_V1_EARLIEST}; requested {start}")

    with store.db() as conn:
        done = {
            json.loads(r["params_json"])["date"]
            for r in conn.execute(
                "SELECT params_json FROM pulls WHERE case_id=? AND source_platform='gdelt_gkg'"
                " AND outcome IN ('success','empty')", (case_id,))
        }

    totals = {"days": 0, "skipped": 0, "records": 0, "failed": 0}
    for day in daterange(start, end):
        iso = day.isoformat()
        if iso in done:
            totals["skipped"] += 1
            continue
        try:
            rows, pull_id = fetch_day(case_id, day, terms)
            store.insert_records([{**r, "case_id": case_id, "pull_id": pull_id} for r in rows])
            totals["days"] += 1
            totals["records"] += len(rows)
            if progress:
                print(f"    {iso}  {len(rows):>5} records", flush=True)
        except GkgUnavailable:
            totals["failed"] += 1
        except Exception as exc:  # noqa: BLE001 — logged in pulls, keep going
            totals["failed"] += 1
            if progress:
                print(f"    {iso}  FAILED {str(exc)[:70]}", flush=True)
    return totals
