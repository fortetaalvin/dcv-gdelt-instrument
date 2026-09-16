"""
Export the provenance database for publication.

Ships `cases`, `pulls` and `daily_counts`. Deliberately omits `records`: those
are 3.34M rows of raw GDELT content, which would be a large redistribution of
someone else's publicly available data. The `pulls` table carries the exact
endpoint, full parameter set and response SHA-256 for every retrieval, so any
figure in the paper can be traced to the request that produced it and the
request can be re-executed against GDELT directly.

`daily_counts` is retained because it is derived aggregate data (one row per
day, not per event) and is the analysis input for the continuous round.
"""
import hashlib, os, sqlite3, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "/var/www/html/dcv/data/dcv.sqlite"
DST = sys.argv[2] if len(sys.argv) > 2 else "/var/www/html/dcv-repo/data/provenance.sqlite"

if os.path.exists(DST):
    os.remove(DST)

src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)

for table in ("cases", "pulls", "daily_counts"):
    ddl = src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone()
    if not ddl:
        print(f"  skip {table}: not present")
        continue
    dst.execute(ddl[0])
    cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
    ph = ",".join("?" * len(cols))
    rows = src.execute(f"SELECT {','.join(cols)} FROM {table}").fetchall()
    dst.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph})", rows)
    dst.commit()
    print(f"  {table:<15}{len(rows):>8,} rows")

# Indexes that make the published database usable.
dst.execute("CREATE INDEX IF NOT EXISTS idx_pull_case ON pulls(case_id, source_platform)")
dst.execute("CREATE INDEX IF NOT EXISTS idx_pull_outcome ON pulls(outcome)")
dst.commit()
dst.execute("VACUUM")
dst.close()
src.close()

size = os.path.getsize(DST)
with open(DST, "rb") as fh:
    digest = hashlib.sha256(fh.read()).hexdigest()
print(f"\n  {DST}")
print(f"  {size/1e6:.2f} MB   sha256 {digest}")
