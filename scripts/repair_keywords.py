"""
Apply keyword repair v3 and validate every term against the corpus.

The validation gate is the point. Round 2's #EndBadGovernance null came from
three of four terms matching literally nothing, and nothing in the pipeline
noticed. A term that returns zero records is now a hard error.
"""
import json, sys, sqlite3
sys.path.insert(0, "/var/www/html/dcv")
from dcv import analysis, store
from dcv.config import DB_PATH

# Live terms kept verbatim; dead terms replaced per PREREGISTRATION_v3.md.
REPAIRED = {
    "chibok_2014":    ["Chibok", "Boko Haram", "Borno", "KIDNAP"],
    "endsars_2020":   ["EndSARS", "Lekki", "SECURITY_SERVICES",
                       "UNREST_POLICEBRUTALITY"],
    "kankara_2020":   ["Kankara", "Katsina", "banditry", "KIDNAP"],
    "plateau_2018":   ["Plateau", "Barkin Ladi", "Jos", "ARMEDCONFLICT"],
    "election_2023":  ["INEC", "Obidient", "PROTEST", "ELECTION"],
    "endbadgov_2024": ["EndBadGovernance", "PROTEST", "ECON_INFLATION"],
}

PREVIOUS = {}
for slug in REPAIRED:
    PREVIOUS[slug] = json.loads(store.get_case(slug)["keywords_json"])

print("=" * 88)
print("  VALIDATION GATE — every term must return > 0 records")
print(f"  {'case':<16}{'term':<26}{'records':>10}  status")
print("  " + "-" * 84)

dead = []
for slug, terms in REPAIRED.items():
    case = store.get_case(slug)
    for t in terms:
        s = analysis.narrative_series(case["case_id"], [t])
        n = int(sum(s.values())) if s else 0
        status = "ok" if n > 0 else "DEAD -- ABORT"
        if n == 0:
            dead.append((slug, t))
        print(f"  {slug:<16}{t:<26}{n:>10,}  {status}")
    print()

if dead:
    print(f"  ABORT: {len(dead)} dead term(s): {dead}")
    raise SystemExit(1)

print("  All terms live. Verifying dropped terms were genuinely inert...")
inert_ok = True
for slug, old in PREVIOUS.items():
    case = store.get_case(slug)
    for t in old:
        if t in REPAIRED[slug]:
            continue
        s = analysis.narrative_series(case["case_id"], [t])
        n = int(sum(s.values())) if s else 0
        if n != 0:
            print(f"    WARNING {slug}: dropped term {t!r} matched {n} records — "
                  f"dropping it DOES change the series")
            inert_ok = False
print("  " + ("every dropped term matched exactly 0 records — the drop is a no-op"
              if inert_ok else "SOME DROPPED TERMS WERE LIVE — see warnings above"))

# Write as a new case version, preserving round-2 specs.
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
print("\n  Writing repaired keyword sets as new case versions...")
for slug, terms in REPAIRED.items():
    old = conn.execute("SELECT * FROM cases WHERE slug=? ORDER BY version DESC LIMIT 1",
                       (slug,)).fetchone()
    spec = {
        "slug": slug, "display_name": old["display_name"],
        "incident_type": old["incident_type"],
        "regions": json.loads(old["regions_json"]),
        "window_start": old["window_start"], "window_end": old["window_end"],
        "trigger_dates": json.loads(old["trigger_dates"]),
        "keywords": terms, "keywords_status": "approved_v3",
        "lead_time_days": old["lead_time_days"],
        "notes": (old["notes"] or "") + " | keywords repaired v3 (2026-09-16).",
    }
    cid = store.upsert_case(spec)
    conn.execute("UPDATE cases SET model_direction=?, lead_time_days=? WHERE case_id=?",
                 (old["model_direction"], old["lead_time_days"], cid))
    conn.commit()
    v = conn.execute("SELECT version FROM cases WHERE case_id=?", (cid,)).fetchone()["version"]
    print(f"    {slug:<16} case_id={cid:<3} version={v}  {terms}")
