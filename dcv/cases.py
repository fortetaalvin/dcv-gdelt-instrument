"""
Case specifications (UC1).

Keyword sets are marked `provisional` deliberately. SAD Open Item 4 requires
Alvin to fix the exact keyword strategy before analysis, because the query set
determines the corpus and therefore every downstream figure. These are a
starting point for discussion, not an approved instrument.
"""
from __future__ import annotations

CHIBOK = {
    "slug": "chibok_2014",
    "display_name": "Chibok schoolgirls abduction",
    "incident_type": "insurgency",
    "regions": ["Borno", "Nigeria"],
    "window_start": "2014-01-01",   # pre-trigger buffer
    "window_end":   "2014-08-31",
    "trigger_dates": ["2014-04-14"],
    "keywords": ["Chibok", "Boko Haram", "schoolgirls abduction", "Borno"],
    "keywords_status": "provisional",
    "lead_time_days": None,         # SAD Open Item 2
    "notes": ("GDELT DOC 2.0 does not index 2014 (verified 2026-09-15). "
              "The narrative layer for this case needs an alternative source; "
              "ground-truth ACLED/UCDP coverage is unaffected."),
}

ENDSARS = {
    "slug": "endsars_2020",
    "display_name": "#EndSARS protest movement",
    "incident_type": "protest movement",
    "regions": ["Lagos", "Nigeria"],
    "window_start": "2020-07-01",   # pre-trigger buffer
    "window_end":   "2020-12-31",
    "trigger_dates": ["2020-10-20"],  # Lekki toll gate
    "keywords": ["EndSARS", "SARS Nigeria", "police brutality Nigeria", "Lekki"],
    "keywords_status": "provisional",
    "lead_time_days": None,         # SAD Open Item 2
    "notes": "Fully within GDELT DOC 2.0 coverage.",
}

ALL = {c["slug"]: c for c in (CHIBOK, ENDSARS)}
