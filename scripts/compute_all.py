"""
Compute every measurement the thesis and the Manara paper support, for all six
cases plus the continuous 11-year series. Emits data/dashboard.json.

Nothing here is new analysis-by-choice: each figure is a construct from one of
the two source documents, or a clearly-marked proposed operationalisation.
"""
import json, sys, time
sys.path.insert(0, "/var/www/html/dcv")
from statistics import mean
from dcv import (analysis, continuous, manara, rolling, store,
                 thesis_metrics as tm)

CASES = ["chibok_2014", "kankara_2020", "plateau_2018",
         "endsars_2020", "election_2023", "endbadgov_2024"]
CLASS = {"chibok_2014": "clandestine", "kankara_2020": "clandestine",
         "plateau_2018": "clandestine", "endsars_2020": "mobilisational",
         "election_2023": "mobilisational", "endbadgov_2024": "mobilisational"}
OUT = "/var/www/html/dcv/data/dashboard.json"

t0 = time.time()
doc = {"cases": {}, "continuous": {}, "meta": {}}

for slug in CASES:
    case = store.get_case(slug)
    did = store.data_case_id(slug)
    trig = min(json.loads(case["trigger_dates"]))
    print(f"  {slug} ...", flush=True)

    # --- Manara TSI ---
    m = manara.compute(did)
    tsi = {d: v["tsi"] for d, v in m.items()}
    cw = {d: v["cw"] for d, v in m.items()}
    ts = {d: v["ts"] for d, v in m.items()}
    ar = {d: v["ar"] for d, v in m.items()}

    # --- structural channels from the case corpus ---
    struct = analysis.structural_series(did)
    prot = {d: v["protest_events"] for d, v in struct.items()}
    gold = {d: v["goldstein"] for d, v in struct.items() if v["goldstein"] is not None}

    chans = {"TSI": tsi, "Cw": cw, "Ts": ts, "Ar": ar,
             "protest_events": prot, "goldstein": gold}

    ch_out = {}
    for name, s in chans.items():
        if len(s) < 33:
            continue
        # Ar and goldstein are inverse-coded: a FALL in explicit conflict
        # language is a RISE in the construct, so they are detected downward
        # only for goldstein; Ar is already oriented so that high = quiet.
        direction = "down" if name == "goldstein" else "up"
        ch_out[name] = {
            "trend": analysis.pre_trigger_trend(s, trig),
            "detection": analysis.detect(s, trig, k=2.0, persistence=2,
                                         direction=direction),
            "surface": analysis.detection_surface(s, trig),
            "series": dict(sorted(s.items())),
        }

    doc["cases"][slug] = {
        "display_name": case["display_name"],
        "incident_type": case["incident_type"],
        "class": CLASS[slug],
        "trigger": trig,
        "window": [case["window_start"], case["window_end"]],
        "keywords": json.loads(case["keywords_json"]),
        "model_direction": case["model_direction"],
        "lead_time_target": case["lead_time_days"],
        "channels": ch_out,
        "epistemic_forgetting": tm.epistemic_forgetting(did),
        "tsi_summary": {
            "tsi_mean": round(mean(tsi.values()), 2),
            "cw_mean": round(mean(cw.values()), 3),
            "ts_mean": round(mean(ts.values()), 3),
            "ar_mean": round(mean(ar.values()), 3),
            "ts_range": [round(min(ts.values()), 3), round(max(ts.values()), 3)],
        },
    }
    print(f"    done [{time.time()-t0:.0f}s]", flush=True)

# --- continuous series ---
print("  continuous ...", flush=True)
prot_c = continuous.series("protest_events")
gold_c = continuous.series("goldstein")
tot_c = continuous.series("total_events")

with store.db() as conn:
    rows = conn.execute("SELECT day, total_events FROM daily_counts ORDER BY day").fetchall()
counts = {r["day"]: {"total_events": r["total_events"]} for r in rows}

TRIGGERS = [doc["cases"][s]["trigger"] for s in CASES]
NEED = set(TRIGGERS)
CLASSES = {"clandestine": {doc["cases"][s]["trigger"] for s in CASES
                           if CLASS[s] == "clandestine"},
           "mobilisational": {doc["cases"][s]["trigger"] for s in CASES
                              if CLASS[s] == "mobilisational"}}

alg = {}
for k in (1.5, 2.0, 2.5, 3.0):
    for p in (2, 3):
        a = tm.algedonic(prot_c, TRIGGERS, k=k, persistence=p)
        det = set(a["hits"].keys())
        a["cvd"] = tm.cvd_jaccard(NEED, det, a["alarms"])
        a["cvd_by_class"] = tm.cvd_by_class(CLASSES, det)
        alg[f"k{k}_p{p}"] = a

doc["continuous"] = {
    "span": [min(prot_c), max(prot_c)], "days": len(prot_c),
    "structural_forgetting": tm.structural_forgetting(counts),
    "cynefin": tm.cynefin_profile(prot_c, gold_c),
    "algedonic": alg,
    "protest_series": prot_c,
    "total_series": tot_c,
}

with store.db() as conn:
    doc["meta"] = {
        "records": conn.execute("SELECT COUNT(*) FROM records").fetchone()[0],
        "pulls": conn.execute("SELECT COUNT(*) FROM pulls").fetchone()[0],
        "daily_counts": conn.execute("SELECT COUNT(*) FROM daily_counts").fetchone()[0],
        "generated": store.now(),
    }

with open(OUT, "w") as fh:
    json.dump(doc, fh, separators=(",", ":"))
import os
print(f"\n  written {OUT}  ({os.path.getsize(OUT)/1e6:.1f} MB)  [{time.time()-t0:.0f}s]")
