"""
Local store: case specifications, normalised ingestion records, pull provenance.

SQLite rather than MariaDB deliberately — this pipeline is self-contained and
single-writer, and a file that can be copied alongside the paper is worth more
for reproducibility than a shared server database.

Every table carries enough provenance to satisfy UC7: any number in the paper
must be traceable back to the exact API call that produced its raw input.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import DB_PATH

SCHEMA = """
-- UC1. Versioned: editing a case spec after a run would silently invalidate
-- the run's provenance, so a change creates a new version instead.
CREATE TABLE IF NOT EXISTS cases (
  case_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  slug           TEXT    NOT NULL,
  version        INTEGER NOT NULL DEFAULT 1,
  display_name   TEXT    NOT NULL,
  incident_type  TEXT    NOT NULL,
  regions_json   TEXT    NOT NULL,
  window_start   TEXT    NOT NULL,
  window_end     TEXT    NOT NULL,
  trigger_dates  TEXT    NOT NULL,   -- JSON list of ground-truth trigger dates
  keywords_json  TEXT    NOT NULL,
  keywords_status TEXT   NOT NULL DEFAULT 'provisional',  -- SAD Open Item 4
  lead_time_days INTEGER NULL,       -- SAD Open Item 2; NULL until fixed
  notes          TEXT    NULL,
  created_at     TEXT    NOT NULL,
  UNIQUE (slug, version)
);

-- One row per API call. The unit of provenance.
CREATE TABLE IF NOT EXISTS pulls (
  pull_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id        INTEGER NOT NULL,
  source_platform TEXT   NOT NULL,   -- gdelt_doc | gdelt_gkg | acled | ucdp_ged | iom_dtm
  endpoint       TEXT    NOT NULL,
  params_json    TEXT    NOT NULL,   -- exact parameters, UC7
  http_status    INTEGER NULL,
  record_count   INTEGER NOT NULL DEFAULT 0,
  response_sha256 TEXT   NULL,
  outcome        TEXT    NOT NULL,   -- success | empty | rate_limited | rejected | error
  error_detail   TEXT    NULL,
  started_at     TEXT    NOT NULL,
  finished_at    TEXT    NULL,
  FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

-- SAD Section 8. One row per normalised record from any source.
CREATE TABLE IF NOT EXISTS records (
  record_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id         INTEGER NOT NULL,
  pull_id         INTEGER NOT NULL,
  source_platform TEXT    NOT NULL,
  source_record_id TEXT   NULL,
  event_date      TEXT    NULL,
  location        TEXT    NULL,
  event_type      TEXT    NULL,
  content_summary TEXT    NULL,
  tone_score      REAL    NULL,
  fatalities      INTEGER NULL,
  retrieval_method TEXT   NOT NULL,
  retrieved_at    TEXT    NOT NULL,
  language        TEXT    NULL,
  graph_node_id   TEXT    NULL,
  raw_json        TEXT    NULL,
  FOREIGN KEY (case_id) REFERENCES cases(case_id),
  FOREIGN KEY (pull_id) REFERENCES pulls(pull_id)
);

CREATE INDEX IF NOT EXISTS idx_rec_case   ON records(case_id, source_platform, event_date);
CREATE INDEX IF NOT EXISTS idx_pull_case  ON pulls(case_id, source_platform, started_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)


def upsert_case(spec: dict[str, Any]) -> int:
    """Insert a case spec, bumping version if the slug already exists with
    different content. Never mutates an existing version."""
    with db() as conn:
        rows = conn.execute(
            "SELECT case_id, version, keywords_json, window_start, window_end, trigger_dates "
            "FROM cases WHERE slug=? ORDER BY version DESC", (spec["slug"],)
        ).fetchall()
        if rows:
            latest = rows[0]
            same = (
                latest["keywords_json"] == json.dumps(spec["keywords"], sort_keys=True)
                and latest["window_start"] == spec["window_start"]
                and latest["window_end"] == spec["window_end"]
                and latest["trigger_dates"] == json.dumps(spec["trigger_dates"], sort_keys=True)
            )
            if same:
                return int(latest["case_id"])
            version = int(latest["version"]) + 1
        else:
            version = 1

        cur = conn.execute(
            "INSERT INTO cases (slug, version, display_name, incident_type, regions_json,"
            " window_start, window_end, trigger_dates, keywords_json, keywords_status,"
            " lead_time_days, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                spec["slug"], version, spec["display_name"], spec["incident_type"],
                json.dumps(spec["regions"], sort_keys=True),
                spec["window_start"], spec["window_end"],
                json.dumps(spec["trigger_dates"], sort_keys=True),
                json.dumps(spec["keywords"], sort_keys=True),
                spec.get("keywords_status", "provisional"),
                spec.get("lead_time_days"), spec.get("notes"), now(),
            ),
        )
        return int(cur.lastrowid)


def get_case(slug: str) -> sqlite3.Row | None:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM cases WHERE slug=? ORDER BY version DESC LIMIT 1", (slug,)
        ).fetchone()


def list_cases() -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM cases GROUP BY slug HAVING version=MAX(version) ORDER BY slug"
        ).fetchall()


def open_pull(case_id: int, platform: str, endpoint: str, params: dict) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO pulls (case_id, source_platform, endpoint, params_json,"
            " outcome, started_at) VALUES (?,?,?,?,'running',?)",
            (case_id, platform, endpoint, json.dumps(params, sort_keys=True), now()),
        )
        return int(cur.lastrowid)


def close_pull(pull_id: int, *, outcome: str, status: int | None = None,
               count: int = 0, sha256: str | None = None, error: str | None = None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE pulls SET outcome=?, http_status=?, record_count=?, response_sha256=?,"
            " error_detail=?, finished_at=? WHERE pull_id=?",
            (outcome, status, count, sha256, error, now(), pull_id),
        )


def insert_records(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    cols = ("case_id", "pull_id", "source_platform", "source_record_id", "event_date",
            "location", "event_type", "content_summary", "tone_score", "fatalities",
            "retrieval_method", "retrieved_at", "language", "raw_json")
    with db() as conn:
        conn.executemany(
            f"INSERT INTO records ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [tuple(r.get(c) for c in cols) for r in rows],
        )
    return len(rows)


def case_summary(case_id: int) -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            "SELECT source_platform, COUNT(*) AS n, MIN(event_date) AS first,"
            " MAX(event_date) AS last FROM records WHERE case_id=?"
            " GROUP BY source_platform ORDER BY source_platform", (case_id,)
        ).fetchall()


def data_case_id(slug: str) -> int:
    """
    The case version that actually owns records for this slug.

    Case specs are versioned, but a keyword repair re-filters data already
    retrieved rather than re-ingesting it, so the new version owns no records
    while the old one owns them all. `get_case` returns the newest spec; this
    returns the id to read records from.

    Raises rather than returning an empty id. A silent empty series is the
    failure mode that let three dead keyword terms go unnoticed through an
    entire analysis round; it is not repeated here.
    """
    with db() as conn:
        rows = conn.execute(
            "SELECT c.case_id, c.version,"
            " (SELECT COUNT(*) FROM records r WHERE r.case_id=c.case_id) n"
            " FROM cases c WHERE c.slug=? ORDER BY c.version DESC", (slug,)).fetchall()
    if not rows:
        raise ValueError(f"unknown case: {slug}")
    owning = [r for r in rows if r["n"] > 0]
    if not owning:
        raise ValueError(f"no version of {slug!r} owns any records — nothing to analyse")
    return int(owning[0]["case_id"])
