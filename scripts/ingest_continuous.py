"""
Continuous Nigeria daily counts, 2014-01-01 to 2024-12-31.

Eleven years spanning all six case triggers, so hits and false alarms are
measured on one series under one rule.
"""
import sys, time, json, sqlite3
sys.path.insert(0, "/var/www/html/dcv")
from dcv import continuous, store
from dcv.config import DB_PATH

START, END = "2014-01-01", "2024-12-31"

# A holder case for provenance. It owns pulls, not records.
spec = {
    "slug": "nigeria_continuous",
    "display_name": "Nigeria continuous daily counts 2014-2024",
    "incident_type": "n/a - continuous baseline",
    "regions": ["Nigeria"],
    "window_start": START, "window_end": END,
    # All six known triggers, so alarms can be scored against every one.
    "trigger_dates": ["2014-04-14", "2018-06-23", "2020-10-20",
                      "2020-12-11", "2023-03-01", "2024-08-01"],
    "keywords": [], "keywords_status": "n/a",
    "lead_time_days": None,
    "notes": ("Continuous baseline for false-alarm measurement. Daily aggregates "
              "only - see dcv/continuous.py for why records are not stored whole."),
}
cid = store.upsert_case(spec)
print(f"  case_id={cid}  {START} .. {END}", flush=True)

t0 = time.time()
totals = continuous.ingest(cid, START, END)
print(f"\n  {totals}", flush=True)
print(f"  elapsed {time.time()-t0:.0f}s", flush=True)
print("DONE", flush=True)
