#!/usr/bin/env python3
"""
Re-executable boundary probes for Section 4.2 of the methods paper.

Every archive-boundary claim in the paper is a live HTTP probe, not a citation.
This script re-runs all of them and prints a PASS/FAIL against the values
recorded in September 2026, so a reviewer can verify the claims today and see
immediately if GDELT's behaviour has since changed.

    python3 probes/boundary_probes.py

Exit status is 0 if every probe matches the recorded expectation, 1 otherwise.
A FAIL is not necessarily an error in the paper: these are dated measurements of
a live service, and the paper states that they carry a half-life. A FAIL means
the boundary has moved, which is itself worth knowing.

No credentials required. All endpoints are public.
"""
from __future__ import annotations

import sys
import time

import requests

TIMEOUT = 60
DOC_INTERVAL = 15.0      # §4.3.1: the documented 5s limit is insufficient
UA = {"User-Agent": "dcv-boundary-probe/1.0 (research reproducibility check)"}
RECORDED = "2026-09-15/16"

# (claim id, description, url, expected_status, paper reference)
HTTP_PROBES = [
    ("B2-a", "Events 2.0 first available 15-min file (2015-02-18 22:45)",
     "http://data.gdeltproject.org/gdeltv2/20150218224500.export.CSV.zip", 200, "§4.2.1"),
    ("B2-b", "Events 2.0 absent six weeks earlier (2015-01-01)",
     "http://data.gdeltproject.org/gdeltv2/20150101000000.export.CSV.zip", 404, "§4.2.1"),
    ("B2-c", "Events 2.0 absent for the Chibok date (2014-04-14)",
     "http://data.gdeltproject.org/gdeltv2/20140414000000.export.CSV.zip", 404, "§4.2.1"),
    ("B3-a", "Events 1.0 present for 2014-04-14 (v1 reaches back)",
     "http://data.gdeltproject.org/events/20140414.export.CSV.zip", 200, "§4.2.2"),
    ("B3-b", "Events 1.0 still written in 2024",
     "http://data.gdeltproject.org/events/20240801.export.CSV.zip", 200, "§4.2.2"),
    ("B3-c", "GKG v1 present for 2014-04-14",
     "http://data.gdeltproject.org/gkg/20140414.gkg.csv.zip", 200, "§4.2.2"),
    ("B3-d", "GKG v1 still written in 2025",
     "http://data.gdeltproject.org/gkg/20250101.gkg.csv.zip", 200, "§4.2.2"),
    ("B4-a", "Archive gap: no GKG file for 2014-03-19",
     "http://data.gdeltproject.org/gkg/20140319.gkg.csv.zip", 404, "§4.2.3"),
    ("B4-b", "Archive gap: no Events file for 2014-03-19",
     "http://data.gdeltproject.org/events/20140319.export.CSV.zip", 404, "§4.2.3"),
    ("B4-c", "Events 1.0 DOES carry 2020-10-20, the date DOC 2.0 lacks",
     "http://data.gdeltproject.org/events/20201020.export.CSV.zip", 200, "§4.2.3"),

    # §4.2.7 — the June-July 2025 outage, present in all four products at once.
    # Found incidentally in September 2026; re-probed six days later and still
    # absent, so it is an archive state rather than a transient fetch failure.
    # The edges matter as much as the absence: the legacy daily file for
    # 2025-06-14 is gone although the 15-minute files cover that day to 17:45.
    ("B5-a", "Outage: GKG v1 absent 2025-06-14 (day exists in 2.0 to 17:45)",
     "http://data.gdeltproject.org/gkg/20250614.gkg.csv.zip", 404, "§4.2.7"),
    ("B5-b", "Outage: Events 1.0 absent 2025-06-18 (same gap, other product)",
     "http://data.gdeltproject.org/events/20250618.export.CSV.zip", 404, "§4.2.7"),
    ("B5-c", "Outage: GKG 2.0 absent 2025-06-18 12:00 (current generation too)",
     "http://data.gdeltproject.org/gdeltv2/20250618120000.gkg.csv.zip", 404, "§4.2.7"),
    ("B5-d", "Outage: Events 2.0 absent 2025-06-18 12:00",
     "http://data.gdeltproject.org/gdeltv2/20250618120000.export.CSV.zip", 404, "§4.2.7"),
    ("B5-e", "Outage left edge: 2.0 present at 2025-06-14 17:45",
     "http://data.gdeltproject.org/gdeltv2/20250614174500.gkg.csv.zip", 200, "§4.2.7"),
    ("B5-f", "Outage left edge: 2.0 absent 15 minutes later, 18:00",
     "http://data.gdeltproject.org/gdeltv2/20250614180000.gkg.csv.zip", 404, "§4.2.7"),
    ("B5-g", "Outage right edge: 2.0 absent at 2025-07-02 01:45",
     "http://data.gdeltproject.org/gdeltv2/20250702014500.gkg.csv.zip", 404, "§4.2.7"),
    ("B5-h", "Outage right edge: 2.0 present at 2025-07-02 02:15",
     "http://data.gdeltproject.org/gdeltv2/20250702021500.gkg.csv.zip", 200, "§4.2.7"),
    ("B5-i", "Boundary control: GKG v1 present the day before (2025-06-13)",
     "http://data.gdeltproject.org/gkg/20250613.gkg.csv.zip", 200, "§4.2.7"),
    ("B5-j", "Boundary control: GKG v1 present the day after (2025-07-02)",
     "http://data.gdeltproject.org/gkg/20250702.gkg.csv.zip", 200, "§4.2.7"),
]


def probe_http(url: str) -> tuple[int | None, str]:
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT, allow_redirects=True,
                         stream=True)
        code = r.status_code
        r.close()
        return code, ""
    except requests.RequestException as exc:
        return None, type(exc).__name__


THROTTLE_MARKERS = ("limit requests", "too many requests", "please limit")


def probe_doc_api(start: str, end: str, retries: int = 3) -> tuple[bool | None, str]:
    """
    DOC 2.0 pre-2017 rejection (§4.2.1).

    Returns (rejected, detail) where `rejected` is None if the API throttled us
    and never gave a usable answer.

    Two of the paper's own findings apply to this function and are worth naming,
    because the first draft of this script fell foul of both. Finding §4.3.1:
    throttling arrives as a plain-text body, sometimes under HTTP 200, so the
    status code cannot be trusted — and a throttle notice contains neither
    "invalid" nor "error", so naive body matching scores it as *acceptance*.
    Finding §4.3.1 again: the documented 5-second limit is insufficient and
    15 seconds is the interval that sustains.
    """
    for attempt in range(retries):
        try:
            r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
                             params={"query": "Nigeria", "mode": "timelinevol",
                                     "startdatetime": start, "enddatetime": end,
                                     "format": "json"},
                             headers=UA, timeout=TIMEOUT)
        except requests.RequestException as exc:
            time.sleep(DOC_INTERVAL)
            if attempt == retries - 1:
                return None, f"request failed: {type(exc).__name__}"
            continue

        body = r.text[:300].strip().replace("\n", " ")
        low = body.lower()
        if r.status_code == 429 or any(m in low for m in THROTTLE_MARKERS):
            time.sleep(DOC_INTERVAL * (attempt + 2))
            continue
        rejected = "invalid" in low or "error" in low
        return rejected, f"HTTP {r.status_code} · {body[:100]}"
    return None, "throttled on every attempt (see §4.3.1)"


def main() -> int:
    print("=" * 78)
    print("  GDELT boundary probes — re-execution of methods paper §4.2")
    print(f"  Expectations recorded {RECORDED}. Probing live endpoints now.")
    print("=" * 78)
    failures = 0
    inconclusive: list[str] = []

    print(f"\n  {'id':<7}{'expect':>7}{'got':>7}  {'result':<7}{'ref':<9}description")
    print("  " + "-" * 74)
    for cid, desc, url, expect, ref in HTTP_PROBES:
        code, err = probe_http(url)
        ok = code == expect
        failures += 0 if ok else 1
        got = str(code) if code is not None else (err or "ERR")
        print(f"  {cid:<7}{expect:>7}{got:>7}  {'PASS' if ok else 'FAIL':<7}{ref:<9}{desc}")
        time.sleep(1.0)

    print("\n  DOC 2.0 date-boundary probes (§4.2.1) — body-inspected, not status-coded")
    print("  " + "-" * 74)
    for cid, start, end, expect_reject, note in [
        ("B1-a", "20170101000000", "20170108000000", False, "2017 accepted"),
        ("B1-b", "20150101000000", "20150108000000", True, "2015 rejected"),
        ("B1-c", "20140401000000", "20140408000000", True, "2014 rejected"),
    ]:
        rejected, detail = probe_doc_api(start, end)
        if rejected is None:
            verdict, skipped = "SKIP", True
        else:
            skipped = False
            ok = rejected == expect_reject
            verdict = "PASS" if ok else "FAIL"
            failures += 0 if ok else 1
        if skipped:
            inconclusive.append(cid)
        print(f"  {cid:<7}{verdict:<7}{note:<16}{detail}")
        time.sleep(DOC_INTERVAL)

    print("\n" + "=" * 78)
    if inconclusive:
        print(f"  {len(inconclusive)} probe(s) inconclusive (throttled): "
              f"{', '.join(inconclusive)}")
        print("  Re-run later; throttling is not a boundary change.")
    if failures:
        print(f"  {failures} probe(s) did not match the recorded values.")
        print("  These are dated measurements of a live service. A mismatch means")
        print("  GDELT's behaviour has changed since September 2026, which the")
        print("  paper anticipates in its Limitations section.")
    else:
        ran = len(HTTP_PROBES) + 3 - len(inconclusive)
        print(f"  {ran} of {len(HTTP_PROBES) + 3} probes ran and all match the values "
              f"recorded {RECORDED}.")
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
