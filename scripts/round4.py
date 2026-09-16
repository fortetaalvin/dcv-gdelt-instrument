"""
Round 4: false-alarm measurement on a continuous 11-year Nigerian series.

This is the test that can only damage the protest-channel finding. Lead times
were measured inside 76-day windows centred on known crises — the least
representative days in the decade. Here the detector runs across every day from
2014 to 2024 under one rolling rule, and every firing is scored against the six
known triggers.

An alarm within `max_lead` days before a trigger is a hit. Every other alarm is
unexplained. "Unexplained" is not the same as "false": Nigeria had crises in
this period beyond our six, and without ACLED or UCDP we cannot enumerate them.
So the unexplained count is an UPPER BOUND on false alarms, and the reported
precision is a LOWER BOUND on true precision. Both are labelled that way.
"""
import json, sys
sys.path.insert(0, "/var/www/html/dcv")
from datetime import date, datetime
from dcv import continuous, rolling

TRIGGERS = {
    "2014-04-14": "Chibok abduction",
    "2018-06-23": "Plateau massacres",
    "2020-10-20": "#EndSARS / Lekki",
    "2020-12-11": "Kankara abduction",
    "2023-03-01": "Election protests",
    "2024-08-01": "#EndBadGovernance",
}
MOBILISATIONAL = {"2020-10-20", "2023-03-01", "2024-08-01"}
MAX_LEAD = 28
OUT = "/var/www/html/dcv/data/round4.json"


def _d(s): return datetime.strptime(s, "%Y-%m-%d").date()


def score(series, k, p, max_lead=MAX_LEAD):
    alarms = rolling.rolling_alarms(series, k=k, persistence=p)
    days = sorted(series)
    observed = len(days) - rolling.BASELINE_WINDOW
    years = observed / 365.25

    explained, hits = set(), {}
    for t in TRIGGERS:
        td = _d(t)
        matched = [a for a in alarms
                   if 0 < (td - _d(a["day"])).days <= max_lead]
        if matched:
            best = max(matched, key=lambda a: (td - _d(a["day"])).days)
            hits[t] = (td - _d(best["day"])).days
            for a in matched:
                explained.add(a["day"])

    unexplained = [a for a in alarms if a["day"] not in explained]
    return {
        "k": k, "persistence": p,
        "observed_days": observed, "years": round(years, 2),
        "alarms": len(alarms),
        "alarms_per_year": round(len(alarms) / years, 2) if years else None,
        "triggers_hit": len(hits), "triggers_total": len(TRIGGERS),
        "mobilisational_hit": sum(1 for t in hits if t in MOBILISATIONAL),
        "clandestine_hit": sum(1 for t in hits if t not in MOBILISATIONAL),
        "hits": hits,
        "unexplained_alarms": len(unexplained),
        "precision_lower_bound": round(len(explained) / len(alarms), 3) if alarms else None,
        "unexplained_days": [a["day"] for a in unexplained],
    }


series = continuous.series("protest_events")
print(f"  continuous series: {len(series)} days "
      f"({min(series)} .. {max(series)})\n")

results = {}
print("=" * 96)
print("  ROUND 4 — continuous rolling detection, protest-event channel")
print(f"  {'k':>5}{'p':>3}{'years':>7}{'alarms':>8}{'per yr':>8}"
      f"{'hits':>7}{'mob':>5}{'clan':>6}{'unexpl':>8}{'precision*':>12}")
print("  " + "-" * 92)
for k in (1.5, 2.0, 2.5, 3.0):
    for p in (2, 3):
        r = score(series, k, p)
        results[f"k{k}_p{p}"] = r
        print(f"  {k:>5}{p:>3}{r['years']:>7.1f}{r['alarms']:>8}"
              f"{r['alarms_per_year']:>8.2f}{r['triggers_hit']:>4}/6"
              f"{r['mobilisational_hit']:>4}/3{r['clandestine_hit']:>4}/3"
              f"{r['unexplained_alarms']:>8}{r['precision_lower_bound']:>12}")

print("\n  * precision is a LOWER BOUND: unexplained alarms may correspond to")
print("    real Nigerian crises outside our six-case list, which we cannot")
print("    enumerate without ACLED or UCDP.")

base = results["k2.0_p2"]
print(f"\n  At the headline setting (k=2.0, p=2): {base['alarms']} alarms in "
      f"{base['years']:.1f} years = {base['alarms_per_year']:.2f}/year")
print(f"  Triggers detected within {MAX_LEAD}d: {base['triggers_hit']}/6")
for t, lead in sorted(base["hits"].items()):
    grp = "mobilisational" if t in MOBILISATIONAL else "clandestine"
    print(f"    {t}  {TRIGGERS[t]:<24}{grp:<16}+{lead}d")
for t in sorted(TRIGGERS):
    if t not in base["hits"]:
        grp = "mobilisational" if t in MOBILISATIONAL else "clandestine"
        print(f"    {t}  {TRIGGERS[t]:<24}{grp:<16}no alarm")

with open(OUT, "w") as fh:
    json.dump(results, fh, indent=1)
print(f"\n  written: {OUT}")
