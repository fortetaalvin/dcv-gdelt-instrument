"""
Fixed analysis parameters (SAD Open Items 2, 5, 9).

Set to values consistent with theoretical norms in conflict early-warning and
content analysis, and fixed HERE, before any analysis run. The SAD is explicit
that the lead-time threshold "must be fixed before running analysis, not derived
post-hoc" — holding these in one module, version-controlled, is what makes that
checkable rather than merely asserted.

Changing a value after a run invalidates that run. Bump PARAMETERS_VERSION and
re-run rather than editing in place.
"""
from __future__ import annotations

PARAMETERS_VERSION = "1.0"
FIXED_ON = "2026-09-15"


# --- Open Item 2: lead-time threshold ---------------------------------------
#
# The SAD's own regression specification (§11) already prescribes sensitivity at
# 1, 2, 4 and 8 weeks. The primary threshold is taken from that ladder rather
# than invented alongside it, so the primary and the sensitivity analysis share
# one scale.
#
# 14 days as primary: conflict early-warning systems operating on structural
# indicators (VIEWS, ACLED CAST) forecast at monthly horizons, but media-narrative
# signals move faster — the #EndSARS build-up ran roughly three weeks. Two weeks
# is long enough for a response to be possible and short enough that narrative
# attention is still plausibly about the coming event rather than the general
# climate.
LEAD_TIME_DAYS = {
    "endsars_2020": 14,
    # Chibok carries no pre-trigger signal (measured: trend 0.64-0.85, declining)
    # and is assigned to Model B, where lead time does not apply. Recorded as
    # None rather than omitted, so the absence is explicit.
    "chibok_2014": None,
}

# Sensitivity ladder, per SAD §11: "1, 2, 4, 8 weeks".
LEAD_TIME_SENSITIVITY_DAYS = [7, 14, 28, 56]


# --- Open Item 5: incident-type taxonomy ------------------------------------
#
# The SAD's first pass is confirmed unchanged. It is actor/phenomenon-based,
# which suits a narrative instrument — but UC-N2 has to match LLM-extracted
# claims against ACLED/UCDP coded events, and those datasets classify by event
# form, not by phenomenon. The mapping below is the addition: without it the
# taxonomy cannot be joined to ground truth.
INCIDENT_TYPES = {
    "insurgency": {
        "acled_event_types": ["Battles", "Explosions/Remote violence",
                              "Violence against civilians"],
        "ucdp_type_of_violence": [1],          # state-based armed conflict
        "note": "Organised armed group vs state or civilians. Chibok sits here.",
    },
    "protest movement": {
        "acled_event_types": ["Protests", "Riots"],
        "ucdp_type_of_violence": [],           # UCDP does not code protest
        "note": ("#EndSARS sits here. UCDP has no protest category, so for this "
                 "type ACLED is the sole ground truth and the ACLED/UCDP "
                 "divergence component of Ts is undefined — see Open Item 7."),
    },
    "banditry/kidnapping": {
        "acled_event_types": ["Violence against civilians", "Battles"],
        "ucdp_type_of_violence": [2, 3],       # non-state, one-sided
        "note": "Profit-motivated armed criminality; overlaps insurgency in coding.",
    },
    "communal violence": {
        "acled_event_types": ["Battles", "Violence against civilians", "Riots"],
        "ucdp_type_of_violence": [2],          # non-state conflict
        "note": "Identity-group violence without a state party.",
    },
    "economic-trigger crisis": {
        "acled_event_types": ["Protests", "Riots", "Strategic developments"],
        "ucdp_type_of_violence": [],
        "note": ("Fuel, currency or subsidy shocks. Largely outside UCDP's "
                 "fatality-threshold coding."),
    },
}


# --- Open Item 9: extraction accuracy validation ----------------------------
#
# Sample size from the standard proportion-estimate calculation: n = 96 gives a
# +/-10 percentage-point margin at 95% confidence for an unknown proportion
# (p = 0.5, worst case). Rounded to 100 per case, which is also the conventional
# floor in content-analysis reliability work.
#
# Thresholds follow Krippendorff's convention: alpha >= 0.80 reliable,
# 0.67-0.80 tentative, below 0.67 unusable. Precision is held to the same bar.
VALIDATION = {
    "sample_size_per_case": 100,
    "sampling": "random without replacement, stratified by pre/post trigger",
    "min_precision": 0.80,          # extracted claims that are correct
    "min_recall": 0.70,             # recall is harder from metadata alone; see note
    "min_agreement_alpha": 0.80,    # if two annotators are used
    "tentative_band": (0.67, 0.80),
    "note": ("Recall is set lower than precision deliberately. Extraction runs "
             "mostly on GKG metadata rather than article text (about 46% text "
             "coverage at 12 years), so a claim absent from the metadata cannot "
             "be recovered and counts against recall through no fault of the "
             "model. Precision is the binding constraint: a false claim "
             "propagates into UC-N2 verification and then into Ts."),
}


# --- Open Item 8: extraction schema -----------------------------------------
# Approved by Alvin 2026-09-15. See dcv/extraction.py.
EXTRACTION_SCHEMA_STATUS = "approved"
EXTRACTION_SCHEMA_APPROVED_ON = "2026-09-15"


def summary() -> str:
    lines = [
        f"  parameters version : {PARAMETERS_VERSION}  (fixed {FIXED_ON})",
        "",
        "  Open Item 2 — lead time",
        f"    primary            : {LEAD_TIME_DAYS}",
        f"    sensitivity ladder : {LEAD_TIME_SENSITIVITY_DAYS} days (SAD §11: 1,2,4,8 weeks)",
        "",
        "  Open Item 5 — incident taxonomy",
    ]
    for name, spec in INCIDENT_TYPES.items():
        lines.append(f"    {name:<24} ACLED={len(spec['acled_event_types'])} types, "
                     f"UCDP={spec['ucdp_type_of_violence'] or 'n/a'}")
    lines += [
        "",
        "  Open Item 9 — validation",
        f"    sample per case    : {VALIDATION['sample_size_per_case']}"
        f"  ({VALIDATION['sampling']})",
        f"    precision >=       : {VALIDATION['min_precision']}",
        f"    recall    >=       : {VALIDATION['min_recall']}",
        f"    alpha     >=       : {VALIDATION['min_agreement_alpha']}",
        "",
        f"  Open Item 8 — extraction schema : {EXTRACTION_SCHEMA_STATUS}"
        f" ({EXTRACTION_SCHEMA_APPROVED_ON})",
    ]
    return "\n".join(lines)
