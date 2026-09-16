"""
Round-2 ingestion: GKG v1 + Events 1.0 for the four falsification cases.

GKG filter terms are deliberately BROAD (country + region + principal actor),
not the narrow pre-registered keyword sets. One broad ingest, many narrow
evaluations: the analysis filters to the frozen keyword set afterwards, so every
candidate framing sees exactly the same underlying corpus.
"""
import sys, time
sys.path.insert(0, "/var/www/html/dcv")
from dcv import events, gkg, store

PLAN = {
    "kankara_2020":   ["Nigeria", "Katsina", "Kankara", "bandit"],
    "plateau_2018":   ["Nigeria", "Plateau", "Jos", "Barkin Ladi"],
    "election_2023":  ["Nigeria", "INEC", "election", "Abuja"],
    "endbadgov_2024": ["Nigeria", "protest", "hunger", "subsidy"],
}

t0 = time.time()
for slug, terms in PLAN.items():
    case = store.get_case(slug)
    cid, a, b = case["case_id"], case["window_start"], case["window_end"]

    print(f"\n### {slug}  GKG  {a} .. {b}  terms={terms}", flush=True)
    g = gkg.ingest_window(cid, a, b, terms, progress=False)
    print(f"    GKG    {g}   [{time.time()-t0:.0f}s]", flush=True)

    print(f"### {slug}  EVENTS  {a} .. {b}", flush=True)
    e = events.ingest_window(cid, a, b, progress=False)
    print(f"    EVENTS {e}   [{time.time()-t0:.0f}s]", flush=True)

print(f"\nDONE in {time.time()-t0:.0f}s", flush=True)
