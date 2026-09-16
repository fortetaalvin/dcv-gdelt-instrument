"""
Seed the four falsification cases. Run BEFORE any retrieval for them.

Windows are trigger-49 .. trigger+26 (76 days), matching the #EndSARS window
exactly so round-2 detection is measured on the same geometry as round 1.
"""
import sys, json, sqlite3
from datetime import datetime, timedelta
sys.path.insert(0, "/var/www/html/dcv")
from dcv import store
from dcv.config import DB_PATH


def window(trigger: str) -> tuple[str, str]:
    t = datetime.strptime(trigger, "%Y-%m-%d").date()
    return (t - timedelta(days=49)).isoformat(), (t + timedelta(days=26)).isoformat()


SPECS = [
    dict(slug="kankara_2020",
         display_name="Kankara schoolboys abduction",
         incident_type="banditry/kidnapping",
         regions=["Katsina", "Nigeria"],
         trigger_dates=["2020-12-11"],
         keywords=["Kankara", "Katsina", "banditry", "schoolboys abduction"],
         model_direction="B", lead_time_days=None,
         notes="Clandestine. Predicted Model B. Pre-registered 2026-09-16."),
    dict(slug="plateau_2018",
         display_name="Plateau State communal massacres",
         incident_type="communal violence",
         regions=["Plateau", "Nigeria"],
         trigger_dates=["2018-06-23"],
         keywords=["Plateau", "Barkin Ladi", "Jos", "herder farmer"],
         model_direction="B", lead_time_days=None,
         notes="Clandestine. Predicted Model B. Pre-registered 2026-09-16."),
    dict(slug="election_2023",
         display_name="2023 presidential election result protests",
         incident_type="protest movement",
         regions=["Abuja", "Lagos", "Nigeria"],
         trigger_dates=["2023-03-01"],
         keywords=["INEC", "election protest", "Obidient",
                   "presidential election Nigeria"],
         model_direction="A", lead_time_days=14,
         notes=("Mobilisational. Predicted Model A, >=14d. CONFOUND recorded in "
                "advance: anchored on a scheduled event, so a positive lead may "
                "measure calendar anticipation rather than crisis anticipation.")),
    dict(slug="endbadgov_2024",
         display_name="#EndBadGovernance hunger protests",
         incident_type="economic-trigger crisis",
         regions=["Kano", "Abuja", "Nigeria"],
         trigger_dates=["2024-08-01"],
         keywords=["EndBadGovernance", "hunger protest", "Nigeria protest",
                   "fuel subsidy"],
         model_direction="A", lead_time_days=14,
         notes="Mobilisational, unscheduled crisis. Predicted Model A, >=14d."),
]

conn = sqlite3.connect(DB_PATH)
cols = {r[1] for r in conn.execute("PRAGMA table_info(cases)")}
if "model_direction" not in cols:
    conn.execute("ALTER TABLE cases ADD COLUMN model_direction TEXT")
    conn.commit()

for spec in SPECS:
    ws, we = window(spec["trigger_dates"][0])
    spec["window_start"], spec["window_end"] = ws, we
    spec["keywords_status"] = "approved"     # frozen by the pre-registration
    cid = store.upsert_case(spec)
    conn.execute("UPDATE cases SET model_direction=?, lead_time_days=? WHERE case_id=?",
                 (spec["model_direction"], spec["lead_time_days"], cid))
    conn.commit()
    print(f"  {spec['slug']:<16} case_id={cid:<3} {ws} .. {we}"
          f"  trigger {spec['trigger_dates'][0]}  Model {spec['model_direction']}"
          f"  target {spec['lead_time_days']}")

print("\nAll six cases:")
for r in conn.execute("SELECT slug, window_start, window_end, trigger_dates,"
                      " model_direction, lead_time_days FROM cases ORDER BY slug"):
    print(f"  {r[0]:<16} {r[1]} .. {r[2]}  trig={json.loads(r[3])[0]}"
          f"  Model {r[4]}  target {r[5]}")
