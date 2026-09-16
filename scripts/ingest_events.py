"""
Ingest GDELT Events 1.0 for both cases.

Windows deliberately match the GKG windows already ingested (76 days each,
centred on the trigger) so the narrative and structural series are measured
over exactly the same span and the comparison is like-for-like.
"""
import sys
sys.path.insert(0, "/var/www/html/dcv")

from dcv import events, store

WINDOWS = {
    "chibok_2014":  ("2014-03-01", "2014-05-15"),
    "endsars_2020": ("2020-09-01", "2020-11-15"),
}

for slug, (start, end) in WINDOWS.items():
    case = store.get_case(slug)
    print(f"\n=== {slug}  {start} .. {end} ===", flush=True)
    totals = events.ingest_window(case["case_id"], start, end, progress=True)
    print(f"  {slug}: {totals}", flush=True)

print("\nDONE", flush=True)
