"""
Continuous daily counts for a country, for false-alarm measurement.

The windowed backtest measures lead time inside 76-day spans centred on known
crises. Those are the least representative days available: every one of them
contains a crisis. An alarm rate computed there says nothing about how often the
detector interrupts an operator during the ordinary months that make up most of
a decade.

This module ingests a long continuous series so that question can be answered.
It can only ever damage the protest-channel finding — a detector that fires
thirty times a year in a country with six crises in a decade is not an early-
warning system, whatever its lead times look like. Confirming the finding would
still require ground truth we do not have; refuting it does not.

**Storage.** Eleven years of Nigerian events is roughly ten million rows. Storing
them whole to answer a question about daily counts would add ~10 GB to the store
for no analytical gain, so this keeps one aggregate row per day. Provenance is
not weakened: every day still writes a `pulls` row with endpoint, parameters,
response hash and outcome, so any count here traces to the bytes it came from.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import zipfile
from datetime import date, datetime, timedelta
from typing import Any, Iterator

import requests

from . import events, store

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_counts (
  day             TEXT NOT NULL,
  country_fips    TEXT NOT NULL,
  pull_id         INTEGER NOT NULL,
  total_events    INTEGER NOT NULL,
  protest_events  INTEGER NOT NULL,   -- CAMEO root 14
  conflict_events INTEGER NOT NULL,   -- QuadClass 4
  fight_events    INTEGER NOT NULL,   -- CAMEO root 19
  assault_events  INTEGER NOT NULL,   -- CAMEO root 18
  goldstein_num   REAL NOT NULL,      -- sum(goldstein * mentions)
  goldstein_den   REAL NOT NULL,      -- sum(mentions)
  tone_sum        REAL NOT NULL,
  tone_n          INTEGER NOT NULL,
  PRIMARY KEY (day, country_fips)
);
"""


def init() -> None:
    with store.db() as conn:
        conn.executescript(SCHEMA)


def daterange(start: str, end: str) -> Iterator[date]:
    a = datetime.strptime(start, "%Y-%m-%d").date()
    b = datetime.strptime(end, "%Y-%m-%d").date()
    while a <= b:
        yield a
        a += timedelta(days=1)


def fetch_day(case_id: int, day: date, fips: str = events.NIGERIA_FIPS) -> dict[str, Any]:
    """Download one Events 1.0 day and reduce it to a single aggregate row."""
    url = f"{events.EVENTS_V1_BASE}/{day.strftime('%Y%m%d')}.export.CSV.zip"
    params = {"date": day.isoformat(), "version": "events_v1",
              "mode": "daily_counts", "country_fips": fips}
    pull_id = store.open_pull(case_id, "gdelt_events_counts", url, params)

    try:
        resp = requests.get(url, timeout=300, allow_redirects=True)
    except requests.RequestException as exc:
        store.close_pull(pull_id, outcome="error", error=str(exc)[:400])
        raise

    if resp.status_code != 200:
        store.close_pull(pull_id, outcome="rejected", status=resp.status_code,
                         error=f"no Events file for {day.isoformat()}")
        raise events.EventsUnavailable(day.isoformat())

    digest = hashlib.sha256(resp.content).hexdigest()
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        text = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, IndexError) as exc:
        store.close_pull(pull_id, outcome="error", status=200, error=str(exc)[:200])
        raise

    agg = {"total_events": 0, "protest_events": 0, "conflict_events": 0,
           "fight_events": 0, "assault_events": 0,
           "goldstein_num": 0.0, "goldstein_den": 0.0, "tone_sum": 0.0, "tone_n": 0}

    for row in csv.reader(io.StringIO(text), delimiter="\t"):
        if len(row) < 52 or not events._is_nigeria(row):
            continue
        agg["total_events"] += 1
        root = events._f(row, "EventRootCode").zfill(2)
        if root == "14":
            agg["protest_events"] += 1
        elif root == "19":
            agg["fight_events"] += 1
        elif root == "18":
            agg["assault_events"] += 1
        if events._num(row, "QuadClass", int) == 4:
            agg["conflict_events"] += 1
        g = events._num(row, "GoldsteinScale")
        m = events._num(row, "NumMentions", int) or 1
        if g is not None:
            agg["goldstein_num"] += g * m
            agg["goldstein_den"] += m
        t = events._num(row, "AvgTone")
        if t is not None:
            agg["tone_sum"] += t
            agg["tone_n"] += 1

    with store.db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO daily_counts (day, country_fips, pull_id,"
            " total_events, protest_events, conflict_events, fight_events,"
            " assault_events, goldstein_num, goldstein_den, tone_sum, tone_n)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (day.isoformat(), fips, pull_id, agg["total_events"],
             agg["protest_events"], agg["conflict_events"], agg["fight_events"],
             agg["assault_events"], agg["goldstein_num"], agg["goldstein_den"],
             agg["tone_sum"], agg["tone_n"]))

    store.close_pull(pull_id, outcome="success" if agg["total_events"] else "empty",
                     status=200, count=agg["total_events"], sha256=digest)
    return agg


def ingest(case_id: int, start: str, end: str,
           fips: str = events.NIGERIA_FIPS, progress_every: int = 50) -> dict[str, int]:
    """Ingest a long range, skipping days already counted. Resumable."""
    init()
    with store.db() as conn:
        done = {r[0] for r in conn.execute(
            "SELECT day FROM daily_counts WHERE country_fips=?", (fips,))}

    totals = {"days": 0, "skipped": 0, "failed": 0, "events": 0}
    n = 0
    for day in daterange(start, end):
        iso = day.isoformat()
        if iso in done:
            totals["skipped"] += 1
            continue
        try:
            agg = fetch_day(case_id, day, fips)
            totals["days"] += 1
            totals["events"] += agg["total_events"]
        except events.EventsUnavailable:
            totals["failed"] += 1
        except Exception as exc:                        # noqa: BLE001
            totals["failed"] += 1
            print(f"    {iso} FAILED {str(exc)[:70]}", flush=True)
        n += 1
        if progress_every and n % progress_every == 0:
            print(f"    {iso}  days={totals['days']} failed={totals['failed']} "
                  f"events={totals['events']:,}", flush=True)
    return totals


def series(metric: str = "protest_events",
           fips: str = events.NIGERIA_FIPS) -> dict[str, float]:
    """Daily series from the aggregate table, ready for the rolling detector."""
    # `goldstein` and `tone` are derived, not stored; everything else is a
    # column. Interpolating a derived name straight into the SELECT is what
    # broke this the first time.
    DERIVED = {"goldstein", "tone"}
    COLUMNS = {"total_events", "protest_events", "conflict_events",
               "fight_events", "assault_events"}

    stem = metric[:-6] + "_events" if metric.endswith("_share") else metric
    if metric not in DERIVED and stem not in COLUMNS:
        raise ValueError(f"unknown metric {metric!r}; "
                         f"expected one of {sorted(COLUMNS | DERIVED)} "
                         f"or a *_share of an event column")

    with store.db() as conn:
        rows = conn.execute(
            "SELECT day, total_events, protest_events, conflict_events,"
            " fight_events, assault_events, goldstein_num, goldstein_den,"
            " tone_sum, tone_n FROM daily_counts WHERE country_fips=?"
            " ORDER BY day", (fips,)).fetchall()

    out: dict[str, float | None] = {}
    for r in rows:
        if metric == "goldstein":
            out[r["day"]] = (r["goldstein_num"] / r["goldstein_den"]
                             if r["goldstein_den"] else None)
        elif metric == "tone":
            out[r["day"]] = r["tone_sum"] / r["tone_n"] if r["tone_n"] else None
        elif metric.endswith("_share"):
            base = r["total_events"]
            out[r["day"]] = r[stem] / base if base else None
        else:
            out[r["day"]] = float(r[metric])
    return {d: v for d, v in out.items() if v is not None}
