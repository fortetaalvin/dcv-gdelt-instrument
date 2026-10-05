#!/usr/bin/env python3
"""
The June-July 2025 GDELT outage: a measurement held for separate publication.

This is NOT part of the methods paper's defect set. The paper reports twenty-three
defects and its §4.2.3 carries a one-sentence qualification pointing at this
measurement; the measurement itself is reserved for a short data note rather than
folded into the paper. It lives here so the evidence is preserved, dated and
re-executable, and so that `boundary_probes.py` continues to correspond exactly to
the claims the paper makes — a reviewer re-running that script should get the
paper, not the paper plus unpublished work.

    python3 probes/outage_2025.py

## What was measured

An outage absent from all four GDELT product generations simultaneously.

    Product      Granularity  Last present       First present after  Missing
    GKG v1       daily        2025-06-13         2025-07-02           18 days
    Events 1.0   daily        2025-06-13         2025-07-02           18 days
    GKG 2.0      15 minutes   2025-06-14 17:45   2025-07-02 02:15     17d 8h
    Events 2.0   15 minutes   2025-06-14 17:45   2025-07-02 02:15     17d 8h

Approximately 1,664 fifteen-minute files are absent. Edges were pinned at
15-minute granularity. First observed 2026-09-28, re-probed 2026-10-04 and
2026-10-05 and still absent, so it is an archive state and not a transient fetch
failure.

## Why it is worth a note of its own

The gaps are *correlated across generations*, because the generations share
upstream infrastructure. The methods paper's §4.2.3 observes that archive gaps
differ between products and that this redundancy performs unintended preservation
work. That holds for the single-day gaps measured there and fails here: when the
upstream pipeline stops, every product stops with it, so a second GDELT product is
not an independent check on the first.

It was found incidentally, in unrelated work, in data a year old at the time, and
we are aware of no published notice of it.

No credentials required. All endpoints are public.
"""
from __future__ import annotations

import sys
import time

import requests

TIMEOUT = 60
UA = {"User-Agent": "dcv-outage-probe/1.0 (research reproducibility check)"}
RECORDED = "2026-09-28, re-probed 2026-10-04 and 2026-10-05"

GKG_V1 = "http://data.gdeltproject.org/gkg/{d}.gkg.csv.zip"
EVENTS_V1 = "http://data.gdeltproject.org/events/{d}.export.CSV.zip"
V2 = "http://data.gdeltproject.org/gdeltv2/{t}.{k}.zip"

# (id, description, url, expected_status)
PROBES = [
    ("O-1", "GKG v1 absent 2025-06-14 (day exists in 2.0 until 17:45)",
     GKG_V1.format(d="20250614"), 404),
    ("O-2", "Events 1.0 absent 2025-06-18 — same gap, different product",
     EVENTS_V1.format(d="20250618"), 404),
    ("O-3", "GKG 2.0 absent 2025-06-18 12:00 — current generation too",
     V2.format(t="20250618120000", k="gkg.csv"), 404),
    ("O-4", "Events 2.0 absent 2025-06-18 12:00",
     V2.format(t="20250618120000", k="export.CSV"), 404),
    ("O-5", "Left edge: 2.0 present at 2025-06-14 17:45",
     V2.format(t="20250614174500", k="gkg.csv"), 200),
    ("O-6", "Left edge: 2.0 absent fifteen minutes later, 18:00",
     V2.format(t="20250614180000", k="gkg.csv"), 404),
    ("O-7", "Right edge: 2.0 absent at 2025-07-02 01:45",
     V2.format(t="20250702014500", k="gkg.csv"), 404),
    ("O-8", "Right edge: 2.0 present at 2025-07-02 02:15",
     V2.format(t="20250702021500", k="gkg.csv"), 200),
    # Controls. Without these the probe cannot distinguish a bounded outage from
    # a broken endpoint or a changed URL scheme.
    ("O-9", "Control: GKG v1 present the day before (2025-06-13)",
     GKG_V1.format(d="20250613"), 200),
    ("O-10", "Control: GKG v1 present the day after (2025-07-02)",
     GKG_V1.format(d="20250702"), 200),
    ("O-11", "Control: GKG v1 present well before (2025-05-01)",
     GKG_V1.format(d="20250501"), 200),
    ("O-12", "Control: GKG v1 present well after (2025-08-01)",
     GKG_V1.format(d="20250801"), 200),
]


def probe(url: str) -> tuple[int | None, str]:
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT, allow_redirects=True,
                         stream=True)
        code = r.status_code
        r.close()
        return code, ""
    except requests.RequestException as exc:
        return None, type(exc).__name__


def main() -> int:
    print("=" * 78)
    print("  GDELT June-July 2025 outage — re-executable measurement")
    print(f"  Expectations recorded {RECORDED}. Probing live endpoints now.")
    print("  Held for separate publication; not part of the methods paper's")
    print("  twenty-three defects. See §4.2.3 of the paper for the qualification.")
    print("=" * 78 + "\n")
    print("  id      expect    got  result  description")
    print("  " + "-" * 74)

    ok = bad = err = 0
    for pid, desc, url, expect in PROBES:
        code, exc = probe(url)
        if code is None:
            result, err = "ERROR", err + 1
            got = exc
        elif code == expect:
            result, ok = "PASS", ok + 1
            got = str(code)
        else:
            result, bad = "FAIL", bad + 1
            got = str(code)
        print(f"  {pid:<7} {expect:>6}  {got:>5}  {result:<6}  {desc}")
        time.sleep(0.4)

    print("\n" + "=" * 78)
    if bad == 0 and err == 0:
        print(f"  All {ok} probes match. The outage is unchanged: still absent from")
        print("  every product generation, edges unmoved at 15-minute granularity.")
    else:
        print(f"  {ok} pass · {bad} fail · {err} could not run")
        print("  A FAIL is not necessarily an error: these are dated measurements of")
        print("  a live service. If the outage has been backfilled, that is worth")
        print("  knowing and the note should say so.")
    print("=" * 78)
    return 1 if bad else (2 if err else 0)


if __name__ == "__main__":
    sys.exit(main())
