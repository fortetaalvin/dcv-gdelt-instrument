"""
Round 3: re-run all six cases with repaired keyword sets.

No re-ingestion. This is a re-filter of data already retrieved, so every
difference from round 2 is attributable to the keyword repair alone.
"""
import json, sys, time
sys.path.insert(0, "/var/www/html/dcv")
from dcv import analysis, store, tsi

CASES = ["chibok_2014", "kankara_2020", "plateau_2018",
         "endsars_2020", "election_2023", "endbadgov_2024"]
OUT = "/var/www/html/dcv/data/round3.json"

results, t0 = {}, time.time()

for slug in CASES:
    case = store.get_case(slug)
    data_id = store.data_case_id(slug)
    trigger = min(json.loads(case["trigger_dates"]))
    terms = json.loads(case["keywords_json"])

    res = analysis.analyse(slug)

    t = tsi.tsi(data_id, terms)
    cw = {d: v["cw"] for d, v in t["cw"].items()}
    ag = {d: v["as_gdelt"] for d, v in t["as"].items()}
    for name, series in (("Cw", cw), ("As", ag),
                         ("TSI_partial", t["tsi_partial"]),
                         ("Ts_proxy", t["ts_proxy"])):
        if len(series) >= 33:
            res["channels"][name] = {
                "n_days": len(series),
                "trend": analysis.pre_trigger_trend(series, trigger),
                "detection": analysis.detect(series, trigger, k=2.0, persistence=2),
                "surface": analysis.detection_surface(series, trigger),
                "series": dict(sorted(series.items())),
            }
    res["tsi_complete"] = t["tsi_complete"]
    res["cw_zero_days"] = sum(1 for v in t["cw"].values() if v["cw"] == 0)
    results[slug] = res
    print("\n" + "=" * 92, flush=True)
    print(analysis.report(res), flush=True)
    print(f"  keywords v{res['spec_version']}: {terms}", flush=True)
    print(f"  [{time.time()-t0:.0f}s]", flush=True)

with open(OUT, "w") as fh:
    json.dump(results, fh, indent=2)
print(f"\n  written: {OUT}  [{time.time()-t0:.0f}s]")
