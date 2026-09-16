"""
Render web/index.html from data/dashboard.json.

The dashboard is an instrument panel, not a document: every figure on it is a
construct from the thesis or the Manara paper, and each is labelled with which.
"""
import json, sys
sys.path.insert(0, "/var/www/html/dcv")

D = json.load(open("/var/www/html/dcv/data/dashboard.json"))
OUT = "/var/www/html/dcv/web/index.html"

CASES = ["chibok_2014", "kankara_2020", "plateau_2018",
         "endsars_2020", "election_2023", "endbadgov_2024"]

# Trim the payload the page actually needs.
payload = {
    "meta": D["meta"],
    "cases": {},
    "continuous": {
        "span": D["continuous"]["span"],
        "days": D["continuous"]["days"],
        "structural_forgetting": D["continuous"]["structural_forgetting"],
        "cynefin": {k: v for k, v in D["continuous"]["cynefin"].items()
                    if k != "per_day"},
        "algedonic": {k: {kk: vv for kk, vv in v.items() if kk != "alarm_days"}
                      for k, v in D["continuous"]["algedonic"].items()},
        "alarm_days": D["continuous"]["algedonic"]["k2.0_p3"]["alarm_days"],
        # Weekly means keep the 11-year chart light without hiding shape.
        "protest_weekly": None,
    },
}

prot = D["continuous"]["protest_series"]
days = sorted(prot)
weekly = []
for i in range(0, len(days) - 6, 7):
    chunk = days[i:i + 7]
    weekly.append([chunk[0], round(sum(prot[d] for d in chunk) / len(chunk), 1)])
payload["continuous"]["protest_weekly"] = weekly

for s in CASES:
    c = D["cases"][s]
    payload["cases"][s] = {
        "display_name": c["display_name"], "class": c["class"],
        "incident_type": c["incident_type"], "trigger": c["trigger"],
        "window": c["window"], "keywords": c["keywords"],
        "lead_time_target": c["lead_time_target"],
        "tsi_summary": c["tsi_summary"],
        "epistemic_forgetting": {k: v for k, v in c["epistemic_forgetting"].items()
                                 if k != "reading"},
        "channels": {
            name: {
                "trend": ch["trend"],
                "detection": ch["detection"],
                "surface": [x for x in ch["surface"] if x["persistence"] == 2],
                "series": ch["series"],
            } for name, ch in c["channels"].items()
        },
    }

js = json.dumps(payload, separators=(",", ":"))

HTML = open("/var/www/html/dcv/web/_dashboard_template.html").read()
html = HTML.replace("/*__DATA__*/null", js)
open(OUT, "w").write(html)
import os
print(f"  written {OUT}  ({os.path.getsize(OUT)/1e6:.2f} MB)")
