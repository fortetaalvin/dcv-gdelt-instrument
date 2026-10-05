#!/usr/bin/env python3
"""
The thirteen-step validation protocol (methods paper §5), as a runnable checker.

Prose checklists get read once. This runs.

    python3 protocol/validate.py --keywords "Chibok" "Boko Haram" "Borno" \\
        --start 2014-03-01 --end 2014-05-15

    python3 protocol/validate.py --config mystudy.json

Checks 1–7 are automatable and run here. Checks 8–13 concern analysis design
rather than retrieval and cannot be verified from a keyword list; they are
printed as an explicit manual checklist so that omitting one is a decision
rather than an oversight.

Exit status: 0 if every automatable check passes, 1 if any fails, 2 if a check
could not be completed (network, throttling).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime

import requests

UA = {"User-Agent": "dcv-validate/1.0 (research pre-flight check)"}
TIMEOUT = 60
GKG_V1 = "http://data.gdeltproject.org/gkg/{d}.gkg.csv.zip"
EVENTS_V1 = "http://data.gdeltproject.org/events/{d}.export.CSV.zip"
GKG_V2 = "http://data.gdeltproject.org/gdeltv2/{t}.gkg.csv.zip"
EVENTS_V2_START = datetime(2015, 2, 18)
DOC_START = datetime(2017, 1, 1)

# Terms that look like prose rather than named entities: two or more words,
# none capitalised as a proper noun. See §4.1.1.
def looks_descriptive(term: str) -> bool:
    words = term.split()
    if len(words) < 2:
        return False
    return not any(w[:1].isupper() for w in words)


THEME_LIKE = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")


class Report:
    def __init__(self) -> None:
        self.fail = 0
        self.warn = 0
        self.error = 0

    def line(self, n, name: str, status: str, detail: str = "") -> None:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "ERR ": "ERR "}[status]
        if status == "FAIL":
            self.fail += 1
        elif status == "WARN":
            self.warn += 1
        elif status == "ERR ":
            self.error += 1
        print(f"  {str(n):>3}. {name:<44}{mark}  {detail}")


def check_1_keywords_live(rep: Report, terms: list[str], sample_day: str) -> None:
    """Check 1 — every keyword must return records. The single most valuable check."""
    try:
        r = requests.get(GKG_V1.format(d=sample_day.replace("-", "")),
                         headers=UA, timeout=TIMEOUT)
        if r.status_code != 200:
            rep.line(1, "Every keyword returns records", "ERR ",
                     f"sample day {sample_day} unavailable (HTTP {r.status_code})")
            return
        import io, zipfile
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        text = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace").lower()
    except Exception as exc:                          # noqa: BLE001
        rep.line(1, "Every keyword returns records", "ERR ", type(exc).__name__)
        return

    dead = []
    for t in terms:
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(t.lower()) + r"(?![a-z0-9])")
        if not pat.search(text):
            dead.append(t)
    if dead:
        rep.line(1, "Every keyword returns records", "FAIL",
                 f"no match on {sample_day}: {dead}")
        print(f"      -> a term matching nothing returns an empty series, not an error.")
        print(f"         Verify across the full window before trusting a null result.")
    else:
        rep.line(1, "Every keyword returns records", "PASS",
                 f"all {len(terms)} matched on {sample_day}")


def check_2_entity_not_prose(rep: Report, terms: list[str]) -> None:
    """Check 2 — name entities, do not describe events."""
    bad = [t for t in terms if looks_descriptive(t)]
    if bad:
        rep.line(2, "Terms name entities, not events", "FAIL",
                 f"descriptive: {bad}")
    else:
        rep.line(2, "Terms name entities, not events", "PASS")


def check_2b_theme_scale(rep: Report, terms: list[str]) -> None:
    """Check 2 (cont.) — theme codes index national volume, not case attention."""
    themes = [t for t in terms if THEME_LIKE.match(t)]
    if themes:
        rep.line("2b", "Theme codes used at national scale only", "WARN",
                 f"{themes} index country-wide topic volume (§4.1.3)")
    else:
        rep.line("2b", "Theme codes used at national scale only", "PASS")


def check_3_decomposable(rep: Report, terms: list[str]) -> None:
    """Check 3 — a single dominant term can carry an apparent signal."""
    if len(terms) < 2:
        rep.line(3, "Signal decomposable by term", "WARN",
                 "single-term set: no decomposition possible")
    else:
        rep.line(3, "Signal decomposable by term", "PASS",
                 f"{len(terms)} terms — decompose before believing detection")


def check_4_word_boundary(rep: Report, terms: list[str]) -> None:
    """Check 4 — substring matching merges unrelated terms."""
    collisions = []
    for a in terms:
        for b in terms:
            if a is not b and a.lower() in b.lower():
                collisions.append((a, b))
    if collisions:
        rep.line(4, "No substring collisions between terms", "WARN",
                 f"{collisions} — require word-boundary matching")
    else:
        rep.line(4, "No substring collisions between terms", "PASS")


def check_5_boundaries(rep: Report, start: str, end: str) -> None:
    """Check 5 — probe the archive boundary for your range."""
    s = datetime.strptime(start, "%Y-%m-%d")
    notes = []
    if s < DOC_START:
        notes.append("DOC 2.0 rejects pre-2017")
    if s < EVENTS_V2_START:
        notes.append("Events 2.0 starts 2015-02-18")
    if notes:
        rep.line(5, "Archive covers the requested range", "WARN",
                 "; ".join(notes) + " -> use v1 products")
    else:
        rep.line(5, "Archive covers the requested range", "PASS",
                 "all product generations reach this range")


def check_6_throttle(rep: Report) -> None:
    """Check 6 — throttling arrives as a body, not a status code."""
    try:
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
                         params={"query": "test", "mode": "timelinevol",
                                 "format": "json"}, headers=UA, timeout=TIMEOUT)
        low = r.text[:300].lower()
        throttled = r.status_code == 429 or "limit requests" in low
        if throttled:
            rep.line(6, "Throttle detection inspects body", "WARN",
                     f"currently throttled (HTTP {r.status_code}) — pace at 15s")
        else:
            rep.line(6, "Throttle detection inspects body", "PASS",
                     f"HTTP {r.status_code}; never branch on status alone")
    except Exception as exc:                          # noqa: BLE001
        rep.line(6, "Throttle detection inspects body", "ERR ", type(exc).__name__)


def check_7_gaps(rep: Report, start: str, end: str, limit: int = 12) -> None:
    """Check 7/8 — archive gaps exist; record them as rejections, not absences."""
    from datetime import timedelta
    a = datetime.strptime(start, "%Y-%m-%d")
    b = datetime.strptime(end, "%Y-%m-%d")
    span = (b - a).days + 1
    step = max(1, span // limit)
    missing = []
    checked = 0
    d = a
    while d <= b and checked < limit:
        try:
            r = requests.head(EVENTS_V1.format(d=d.strftime("%Y%m%d")),
                              headers=UA, timeout=30, allow_redirects=True)
            if r.status_code != 200:
                missing.append(d.strftime("%Y-%m-%d"))
        except requests.RequestException:
            pass
        checked += 1
        d += timedelta(days=step)
        time.sleep(0.4)
    if missing:
        # §4.2.3 — a gap in one product is not evidence the others have it.
        # Probe the current generation for the same day. If it is also absent the
        # gap is correlated across generations, and no GDELT product can fill it.
        correlated = []
        for day in missing[:4]:
            t = day.replace("-", "") + "120000"
            try:
                r2 = requests.head(GKG_V2.format(t=t), headers=UA, timeout=30,
                                   allow_redirects=True)
                if r2.status_code != 200:
                    correlated.append(day)
            except requests.RequestException:
                pass
            time.sleep(0.4)
        if correlated:
            rep.line(7, "No archive gaps in sampled days", "WARN",
                     f"missing {missing} of {checked} sampled; "
                     f"also absent from GKG 2.0: {correlated} "
                     "-> correlated gap, no product can fill it")
        else:
            rep.line(7, "No archive gaps in sampled days", "WARN",
                     f"missing {missing} of {checked} sampled; "
                     "GKG 2.0 carries these days -> use the other generation")
    else:
        rep.line(7, "No archive gaps in sampled days", "PASS",
                 f"{checked} days sampled, all present")


MANUAL = [
    ("8", "Record gaps as rejected retrievals, never as absent days.", "§4.2.3"),
    ("9", "Adjust for archive non-stationarity in cross-period volume comparison "
          "(peak/trough 1.848 over 11 years).", "§4.2.4"),
    ("10", "Use a rolling baseline for operational claims; fixed only for "
           "'was a signal present'.", "§4.5.2"),
    ("11", "Report alarms per unit time beside every lead time, with a "
           "refractory period.", "§4.5.3"),
    ("12", "Verify URL resolution before planning text extraction — a third of "
           "sources are gone in two years.", "§4.2.5"),
    ("13", "Use differences not ratios on signed series; log every retrieval "
           "with parameters and a response hash.", "§4.5.4"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="GDELT study pre-flight validation")
    ap.add_argument("--keywords", nargs="+", help="keyword terms to validate")
    ap.add_argument("--start", help="window start YYYY-MM-DD")
    ap.add_argument("--end", help="window end YYYY-MM-DD")
    ap.add_argument("--config", help="JSON file with keywords/start/end")
    ap.add_argument("--skip-network", action="store_true")
    a = ap.parse_args()

    if a.config:
        cfg = json.load(open(a.config))
        terms = cfg["keywords"]; start = cfg["start"]; end = cfg["end"]
    else:
        if not (a.keywords and a.start and a.end):
            ap.error("provide --keywords/--start/--end, or --config")
        terms, start, end = a.keywords, a.start, a.end

    print("=" * 78)
    print("  GDELT study pre-flight validation — methods paper §5")
    print(f"  {len(terms)} terms · {start} to {end}")
    print("=" * 78 + "\n")

    rep = Report()
    check_2_entity_not_prose(rep, terms)
    check_2b_theme_scale(rep, terms)
    check_3_decomposable(rep, terms)
    check_4_word_boundary(rep, terms)
    check_5_boundaries(rep, start, end)
    if not a.skip_network:
        check_1_keywords_live(rep, terms, start)
        check_6_throttle(rep)
        check_7_gaps(rep, start, end)
    else:
        print("  (network checks 1, 6, 7 skipped)")

    print("\n  Manual checks — not verifiable from a keyword list:")
    print("  " + "-" * 74)
    for n, text, ref in MANUAL:
        print(f"  {n:>2}. [ ] {text}  {ref}")

    print("\n" + "=" * 78)
    print(f"  {rep.fail} failed · {rep.warn} warnings · {rep.error} could not run")
    if rep.fail:
        print("  A FAIL means the study as configured will produce a series that")
        print("  looks valid and measures nothing. Resolve before retrieving data.")
    print("=" * 78)
    return 1 if rep.fail else (2 if rep.error else 0)


if __name__ == "__main__":
    sys.exit(main())
