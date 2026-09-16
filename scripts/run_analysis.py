"""
Full analysis run for both cases. Writes JSON for the paper and prints tables.
"""
import json, sys
sys.path.insert(0, "/var/www/html/dcv")
from dcv import analysis, parameters, store, events

OUT = "/var/www/html/dcv/data/analysis.json"
results = {}

for slug in ("chibok_2014", "endsars_2020"):
    res = analysis.analyse(slug)
    results[slug] = res
    print("\n" + "=" * 86)
    print(analysis.report(res))

    # Detection surface: does early warning survive the parameter sweep, or
    # exist only in one corner of it?
    print(f"\n  DETECTION SURFACE — {slug}")
    print(f"    {'channel':<26}{'k=1.5':>18}{'k=2.0':>18}{'k=2.5':>18}{'k=3.0':>18}")
    for name, c in res["channels"].items():
        if "surface" not in c:
            continue
        cells = []
        for k in (1.5, 2.0, 2.5, 3.0):
            hits = [s for s in c["surface"] if s["k"] == k and s["persistence"] == 2]
            s = hits[0] if hits else None
            cells.append(f"{s['lead_days']:+d}d" if s and s.get("fired") else "none")
        print(f"    {name:<26}" + "".join(f"{x:>18}" for x in cells))

# Coverage accounting — gaps must be visible, not silently absent.
print("\n" + "=" * 86)
print("  ARCHIVE COVERAGE")
for slug, (a, b) in {"chibok_2014": ("2014-03-01", "2014-05-15"),
                     "endsars_2020": ("2020-09-01", "2020-11-15")}.items():
    case = store.get_case(slug)
    with store.db() as conn:
        for plat in ("gdelt_gkg", "gdelt_events"):
            got = {r[0] for r in conn.execute(
                "SELECT DISTINCT event_date FROM records WHERE case_id=? AND source_platform=?",
                (case["case_id"], plat))}
            want = {d.isoformat() for d in events.daterange(a, b)}
            miss = sorted(want - got)
            print(f"    {slug:<14} {plat:<14} {len(got)}/{len(want)} days"
                  f"   missing: {miss or 'none'}")
            results.setdefault(slug, {}).setdefault("coverage", {})[plat] = {
                "have": len(got), "want": len(want), "missing": miss}

with open(OUT, "w") as fh:
    json.dump(results, fh, indent=2)
print(f"\n  written: {OUT}")
