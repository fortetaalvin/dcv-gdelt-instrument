"""
Round-2 analysis: all six cases, detection + TSI components.

Focal terms for Cw are the case's frozen keyword set, used verbatim. Terms that
do not appear as GKG entities simply contribute nothing; no new term is
introduced at analysis time, so this adds no researcher degrees of freedom.
"""
import json, sys, time
sys.path.insert(0, "/var/www/html/dcv")
from statistics import mean
from dcv import analysis, store, tsi

CASES = ["chibok_2014", "endsars_2020", "kankara_2020", "plateau_2018",
         "election_2023", "endbadgov_2024"]
OUT = "/var/www/html/dcv/data/round2.json"

results = {}
t0 = time.time()

for slug in CASES:
    case = store.get_case(slug)
    if case is None:
        print(f"  {slug}: MISSING"); continue
    trigger = min(json.loads(case["trigger_dates"]))
    terms = json.loads(case["keywords_json"])

    res = analysis.analyse(slug)

    # TSI components
    t = tsi.tsi(case["case_id"], terms)
    cw = {d: v["cw"] for d, v in t["cw"].items()}
    ag = {d: v["as_gdelt"] for d, v in t["as"].items()}
    part = t["tsi_partial"]

    for name, series in (("Cw", cw), ("As", ag), ("TSI_partial", part),
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
    res["tsi_complete_reason"] = t["tsi_complete_reason"]
    res["cw_detail"] = t["cw"]
    results[slug] = res

    print("\n" + "=" * 92, flush=True)
    print(analysis.report(res), flush=True)
    print(f"  [{time.time()-t0:.0f}s]", flush=True)

with open(OUT, "w") as fh:
    json.dump(results, fh, indent=2)

# ---- the falsification table -------------------------------------------
print("\n" + "=" * 92)
print("  PRE-REGISTERED PREDICTIONS vs OUTCOME")
print(f"  {'case':<16}{'type':<24}{'pred':>6}{'target':>8}{'lead(k=2)':>11}"
      f"{'lead(k=3)':>11}{'verdict':>10}")
print("  " + "-" * 88)
for slug in CASES:
    if slug not in results:
        continue
    res = results[slug]
    case = store.get_case(slug)
    ch = res["channels"].get("narrative_keyword", {})
    d2 = ch.get("detection", {})
    s3 = [s for s in ch.get("surface", []) if s["k"] == 3.0 and s["persistence"] == 2]
    l2 = d2.get("lead_days") if d2.get("fired") else None
    l3 = s3[0].get("lead_days") if s3 and s3[0].get("fired") else None
    pred = res["model_direction"]
    tgt = res["lead_time_target_days"]
    best = max([x for x in (l2, l3) if x is not None], default=None)
    if pred == "A":
        ok = best is not None and tgt is not None and best >= tgt
        verdict = "MET" if ok else "MISSED"
    else:
        ok = best is None or best <= 0
        verdict = "CONFIRMED" if ok else "REFUTED"
    print(f"  {slug:<16}{case['incident_type']:<24}{pred:>6}"
          f"{str(tgt):>8}{str(l2):>11}{str(l3):>11}{verdict:>10}")

print(f"\n  written: {OUT}   [{time.time()-t0:.0f}s]")
