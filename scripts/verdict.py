"""
Falsification verdict + cross-case channel comparison, read from round2.json.

Verdict targets come from the CASE ROW (where the pre-registration wrote them),
not from parameters.LEAD_TIME_DAYS, which only ever held the two round-1 cases.
The earlier run read the wrong source and reported round-2 targets as None,
which turned a met target into "MISSED".
"""
import json, sys
sys.path.insert(0, "/var/www/html/dcv")
from dcv import store

R = json.load(open("/var/www/html/dcv/data/round2.json"))
CASES = ["chibok_2014", "endsars_2020", "kankara_2020", "plateau_2018",
         "election_2023", "endbadgov_2024"]
GROUP = {"chibok_2014": "clandestine", "kankara_2020": "clandestine",
         "plateau_2018": "clandestine", "endsars_2020": "mobilisational",
         "election_2023": "mobilisational", "endbadgov_2024": "mobilisational"}


def leads(res, channel):
    ch = res["channels"].get(channel, {})
    out = {}
    for s in ch.get("surface", []):
        if s["persistence"] == 2:
            out[s["k"]] = s.get("lead_days") if s.get("fired") else None
    return out


print("=" * 94)
print("  PRE-REGISTERED PREDICTIONS vs OUTCOME   (channel: narrative_keyword, p=2)")
print(f"  {'case':<16}{'group':<15}{'pred':>5}{'target':>7}"
      f"{'k=1.5':>7}{'k=2.0':>7}{'k=2.5':>7}{'k=3.0':>7}{'verdict':>12}")
print("  " + "-" * 90)

verdicts = {}
for slug in CASES:
    res, case = R[slug], store.get_case(slug)
    tgt = case["lead_time_days"]          # pre-registered, from the case row
    L = leads(res, "narrative_keyword")
    pos = [v for v in L.values() if v is not None and v > 0]
    if res["model_direction"] == "A":
        ok = bool(pos) and max(pos) >= (tgt or 0)
        v = "MET" if ok else "MISSED"
    else:
        # Falsification condition from the pre-registration: a clandestine case
        # firing with lead >= 7 days refutes H1.
        strong = [x for x in pos if x >= 7]
        v = "REFUTED" if strong else "CONFIRMED"
    verdicts[slug] = v
    cells = "".join(f"{(str(L.get(k)) if L.get(k) is not None else '--'):>7}"
                    for k in (1.5, 2.0, 2.5, 3.0))
    print(f"  {slug:<16}{GROUP[slug]:<15}{res['model_direction']:>5}"
          f"{str(tgt):>7}{cells}{v:>12}")

print()
nA = [s for s in CASES if GROUP[s] == "mobilisational"]
nB = [s for s in CASES if GROUP[s] == "clandestine"]
print(f"  clandestine   : {sum(1 for s in nB if verdicts[s]=='CONFIRMED')}/{len(nB)} confirmed")
print(f"  mobilisational: {sum(1 for s in nA if verdicts[s]=='MET')}/{len(nA)} met target")

# ---- which channel is actually the best detector? ---------------------
print()
print("=" * 94)
print("  LEAD TIME BY CHANNEL, ALL CASES (k=2.0, p=2).  '--' = never fired")
chans = ["narrative_keyword", "structural_protest_events", "structural_protest_share",
         "structural_conflict_share", "structural_goldstein", "Cw", "As",
         "TSI_partial", "Ts_proxy"]
print(f"  {'channel':<28}" + "".join(f"{s.split('_')[0][:9]:>11}" for s in CASES))
print("  " + "-" * 90)
for c in chans:
    row = ""
    for slug in CASES:
        ch = R[slug]["channels"].get(c, {})
        d = ch.get("detection", {})
        row += f"{(str(d.get('lead_days')) if d.get('fired') else '--'):>11}"
    print(f"  {c:<28}{row}")

print()
print("  Positive = days of early warning. Clandestine cases are columns 1,3,4;")
print("  mobilisational are 2,5,6.")

# ---- does TSI add anything over the plain narrative channel? ----------
print()
print("=" * 94)
print("  DOES TSI IMPROVE ON THE NARRATIVE CHANNEL?")
print(f"  {'case':<16}{'narrative':>11}{'Cw':>8}{'As':>8}{'TSI_partial':>13}{'best':>14}")
print("  " + "-" * 72)
for slug in CASES:
    ch = R[slug]["channels"]
    def L(c):
        d = ch.get(c, {}).get("detection", {})
        return d.get("lead_days") if d.get("fired") else None
    n, cw, a, t = L("narrative_keyword"), L("Cw"), L("As"), L("TSI_partial")
    vals = {"narrative": n, "Cw": cw, "As": a, "TSI_partial": t}
    pos = {k: v for k, v in vals.items() if v is not None and v > 0}
    best = max(pos, key=pos.get) + f" (+{pos[max(pos, key=pos.get)]})" if pos else "none fired"
    f = lambda x: str(x) if x is not None else "--"
    print(f"  {slug:<16}{f(n):>11}{f(cw):>8}{f(a):>8}{f(t):>13}{best:>14}")

print()
print("  Ts is absent from every row: it requires ACLED/UCDP ground truth and")
print("  UC-N2 claim verification, neither of which exists. No complete TSI was")
print("  computed for any case.")
