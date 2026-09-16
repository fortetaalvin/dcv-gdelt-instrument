"""One worker over a date range. Resumable: skips days already counted."""
import sys, time
sys.path.insert(0, "/var/www/html/dcv")
from dcv import continuous, store

start, end = sys.argv[1], sys.argv[2]
cid = store.get_case("nigeria_continuous")["case_id"]
t0 = time.time()
totals = continuous.ingest(cid, start, end, progress_every=100)
print(f"\n  {start}..{end}  {totals}  elapsed {time.time()-t0:.0f}s", flush=True)
print("DONE", flush=True)
