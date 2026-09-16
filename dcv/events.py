"""
GDELT Events ingestion (UC2, structural-intensity layer).

GKG tells us what was *said*; Events tells us what was *coded to have happened*,
in CAMEO, with a Goldstein conflict-intensity score attached. That numeric
intensity series is what the narrative-only pipeline lacked.

Version choice, measured 2026-09-15 rather than assumed:

    GET gdeltv2/20150101000000.export.CSV.zip -> 404
    GET gdeltv2/20150218224500.export.CSV.zip -> 200   <- v2 begins here
    GET gdeltv2/20140414000000.export.CSV.zip -> 404
    GET events/20140414.export.CSV.zip        -> 200   9.8 MB
    GET events/20201020.export.CSV.zip        -> 200   7.2 MB

Events 2.0 starts **2015-02-18 22:45** and therefore cannot reach Chibok — the
same boundary problem that forced GKG v1 for the narrative layer. Events 1.0
daily files cover both cases, so **v1 is the primary source for both**, which
keeps the two cases comparable. v2 is available for #EndSARS as a
higher-resolution robustness check only.

v1 is 58 tab-delimited columns, no header, no quoting (verified against
2014-04-14: 142,038 rows). Rows are filtered to Nigeria at parse time — a day is
~10 MB and the two windows are 152 days, so storing whole files would cost
~1.5 GB to answer a question about one country.

One subtlety that matters for the analysis: a row's SQLDATE is when the event
is said to have occurred, which is often years before the article. The Chibok
file's very first row is a 2004 event. For a *media-attention* series the
meaningful date is DATEADDED — the day the coverage appeared — so that is what
lands in `event_date`, with SQLDATE preserved in `raw_json`.
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

EVENTS_V1_BASE = "http://data.gdeltproject.org/events"
EVENTS_V2_BASE = "http://data.gdeltproject.org/gdeltv2"
EVENTS_V2_EARLIEST = "2015-02-18"

# FIPS 10-4, which is what GDELT geocoding uses. Nigeria is NI, not NG.
NIGERIA_FIPS = "NI"
NIGERIA_ISO3 = "NGA"

csv.field_size_limit(sys.maxsize)

# 58-column v1 layout, by index. Only the columns the analysis touches.
COL = {
    "GLOBALEVENTID": 0, "SQLDATE": 1, "Actor1Code": 5, "Actor1Name": 6,
    "Actor1CountryCode": 7, "Actor1Type1Code": 12, "Actor2Code": 15,
    "Actor2Name": 16, "Actor2CountryCode": 17, "Actor2Type1Code": 22,
    "IsRootEvent": 25, "EventCode": 26, "EventBaseCode": 27, "EventRootCode": 28,
    "QuadClass": 29, "GoldsteinScale": 30, "NumMentions": 31, "NumSources": 32,
    "NumArticles": 33, "AvgTone": 34,
    "Actor1Geo_CountryCode": 37, "Actor2Geo_CountryCode": 44,
    "ActionGeo_Type": 49, "ActionGeo_FullName": 50, "ActionGeo_CountryCode": 51,
    "ActionGeo_ADM1Code": 52, "ActionGeo_Lat": 53, "ActionGeo_Long": 54,
    "DATEADDED": 56, "SOURCEURL": 57,
}

# CAMEO root codes 14 (protest), 18 (assault), 19 (fight), 20 (mass violence).
# QuadClass 4 is "material conflict". Kept as names so the taxonomy join in
# parameters.INCIDENT_TYPES has something legible to match on.
QUAD_CLASS = {1: "verbal_cooperation", 2: "material_cooperation",
              3: "verbal_conflict", 4: "material_conflict"}

EVENT_ROOT = {
    "01": "public_statement", "02": "appeal", "03": "express_intent",
    "04": "consult", "05": "diplomatic_cooperation", "06": "material_cooperation",
    "07": "provide_aid", "08": "yield", "09": "investigate", "10": "demand",
    "11": "disapprove", "12": "reject", "13": "threaten", "14": "protest",
    "15": "exhibit_force", "16": "reduce_relations", "17": "coerce",
    "18": "assault", "19": "fight", "20": "mass_violence",
}


class EventsUnavailable(RuntimeError):
    pass


def _day_url_v1(d: date) -> str:
    return f"{EVENTS_V1_BASE}/{d.strftime('%Y%m%d')}.export.CSV.zip"


def daterange(start: str, end: str) -> Iterator[date]:
    a = datetime.strptime(start, "%Y-%m-%d").date()
    b = datetime.strptime(end, "%Y-%m-%d").date()
    while a <= b:
        yield a
        a += timedelta(days=1)


def _f(row: list[str], key: str) -> str:
    i = COL[key]
    return row[i] if i < len(row) else ""


def _num(row: list[str], key: str, cast=float):
    try:
        return cast(_f(row, key))
    except (TypeError, ValueError):
        return None


def _is_nigeria(row: list[str]) -> bool:
    """
    Geography first, actors second.

    Matching on actor country alone would sweep in events that merely involve a
    Nigerian actor abroad; matching on ActionGeo alone would drop events about
    Nigeria attributed to a foreign actor with no geocode. Both are wanted, so
    both are tested — and which one fired is recorded, so the mix is auditable
    rather than a hidden filter decision.
    """
    return (_f(row, "ActionGeo_CountryCode") == NIGERIA_FIPS
            or _f(row, "Actor1Geo_CountryCode") == NIGERIA_FIPS
            or _f(row, "Actor2Geo_CountryCode") == NIGERIA_FIPS
            or _f(row, "Actor1CountryCode") == NIGERIA_ISO3
            or _f(row, "Actor2CountryCode") == NIGERIA_ISO3)


def _match_reason(row: list[str]) -> str:
    if _f(row, "ActionGeo_CountryCode") == NIGERIA_FIPS:
        return "action_geo"
    if _f(row, "Actor1Geo_CountryCode") == NIGERIA_FIPS or \
       _f(row, "Actor2Geo_CountryCode") == NIGERIA_FIPS:
        return "actor_geo"
    return "actor_country"


def _normalise(row: list[str], day: date, method: str, retrieved: str) -> dict[str, Any]:
    root = _f(row, "EventRootCode").zfill(2)
    quad = _num(row, "QuadClass", int)
    goldstein = _num(row, "GoldsteinScale")
    return {
        "source_platform": "gdelt_events",
        "source_record_id": _f(row, "GLOBALEVENTID"),
        # DATEADDED, not SQLDATE — see module docstring.
        "event_date": day.isoformat(),
        "event_type": EVENT_ROOT.get(root, f"cameo_{root}"),
        "location": (_f(row, "ActionGeo_FullName") or "")[:255] or None,
        "content_summary": None,          # Events carries no prose; GKG has that
        "tone_score": _num(row, "AvgTone"),
        "fatalities": None,               # CAMEO does not code fatality counts
        "language": None,
        "retrieval_method": method,
        "retrieved_at": retrieved,
        "raw_json": json.dumps({
            "sqldate": _f(row, "SQLDATE"),
            "event_code": _f(row, "EventCode"),
            "event_base_code": _f(row, "EventBaseCode"),
            "event_root_code": root,
            "quad_class": quad,
            "quad_class_name": QUAD_CLASS.get(quad),
            "goldstein": goldstein,
            "is_root_event": _num(row, "IsRootEvent", int),
            "num_mentions": _num(row, "NumMentions", int),
            "num_sources": _num(row, "NumSources", int),
            "num_articles": _num(row, "NumArticles", int),
            "actor1": _f(row, "Actor1Name"), "actor2": _f(row, "Actor2Name"),
            "actor1_country": _f(row, "Actor1CountryCode"),
            "actor2_country": _f(row, "Actor2CountryCode"),
            "actor1_type": _f(row, "Actor1Type1Code"),
            "actor2_type": _f(row, "Actor2Type1Code"),
            "adm1": _f(row, "ActionGeo_ADM1Code"),
            "lat": _num(row, "ActionGeo_Lat"), "lon": _num(row, "ActionGeo_Long"),
            "match_reason": _match_reason(row),
            "sourceurl": _f(row, "SOURCEURL"),
        }, sort_keys=True),
    }


def fetch_day(case_id: int, day: date) -> tuple[list[dict[str, Any]], int]:
    """Download one Events 1.0 day, keep Nigeria rows, normalise to SAD §8."""
    url = _day_url_v1(day)
    params = {"date": day.isoformat(), "version": "events_v1",
              "filter": f"ActionGeo/Actor == {NIGERIA_FIPS}/{NIGERIA_ISO3}"}
    pull_id = store.open_pull(case_id, "gdelt_events", url, params)

    try:
        resp = requests.get(url, timeout=300, allow_redirects=True)
    except requests.RequestException as exc:
        store.close_pull(pull_id, outcome="error", error=str(exc)[:400])
        raise

    if resp.status_code != 200:
        store.close_pull(pull_id, outcome="rejected", status=resp.status_code,
                         error=f"no Events file for {day.isoformat()}")
        raise EventsUnavailable(f"Events v1 has no file for {day.isoformat()}")

    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        text = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, IndexError) as exc:
        store.close_pull(pull_id, outcome="error", status=200, error=str(exc)[:200])
        raise

    retrieved = store.now()
    method = f"GET {url} (filtered to Nigeria at parse time)"
    rows = [_normalise(r, day, method, retrieved)
            for r in csv.reader(io.StringIO(text), delimiter="\t")
            if len(r) >= 52 and _is_nigeria(r)]

    store.close_pull(pull_id, outcome="success" if rows else "empty",
                     status=200, count=len(rows))
    return rows, pull_id


def ingest_window(case_id: int, start: str, end: str,
                  progress: bool = True) -> dict[str, int]:
    """Ingest a date range. Skips days already pulled for this case."""
    with store.db() as conn:
        done = {
            json.loads(r["params_json"])["date"]
            for r in conn.execute(
                "SELECT params_json FROM pulls WHERE case_id=?"
                " AND source_platform='gdelt_events'"
                " AND outcome IN ('success','empty')", (case_id,))
        }

    totals = {"days": 0, "skipped": 0, "records": 0, "failed": 0}
    for day in daterange(start, end):
        iso = day.isoformat()
        if iso in done:
            totals["skipped"] += 1
            continue
        try:
            rows, pull_id = fetch_day(case_id, day)
            store.insert_records([{**r, "case_id": case_id, "pull_id": pull_id}
                                  for r in rows])
            totals["days"] += 1
            totals["records"] += len(rows)
            if progress:
                print(f"    {iso}  {len(rows):>5} Nigeria events", flush=True)
        except EventsUnavailable:
            totals["failed"] += 1
        except Exception as exc:                      # noqa: BLE001
            totals["failed"] += 1
            if progress:
                print(f"    {iso}  FAILED {str(exc)[:70]}", flush=True)
    return totals
