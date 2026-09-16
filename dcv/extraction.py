"""
UC-N1 extraction schema — APPROVED 2026-09-15 (SAD Open Item 8).

Proposed by Claude Code and approved by Alvin on 2026-09-15. The SAD requires approval
before this is treated as fixed, "since it determines what the graph can
represent". It is now fixed; changes require a schema-version bump.

Three measurements shaped this design, all taken 2026-09-15:

1. **GKG already extracts entities.** Every record carries PERSONS,
   ORGANIZATIONS and geocoded LOCATIONS from GDELT's own pipeline. Having an
   8B model re-extract them would be slower, worse, and would introduce error
   into data that arrives clean. The model's genuine contribution is what GKG
   does NOT provide: *relations* between actors, and *discrete claims* that
   UC-N2 can check against ground truth.

2. **Article text is not reliably available for 2014.** Sampling Chibok source
   URLs: 5 of 15 still resolve (67% link rot), and Wayback recovers roughly 1 in
   5 of the remainder — about 46% total coverage.

3. **Rot is roughly uniform, not differentially Nigerian.** A first eyeball
   suggested local outlets had died while international ones survived. A
   systematic split does not support that: 78% rot in both pre- and
   post-trigger periods, with no established source-origin effect at n=14 per
   group. UC8 should still report source representation as a named limitation
   distinct from LLM extraction error — but on measured grounds, not this one.

Hence: extraction operates on the **structured GKG record**, with article text
as optional enrichment when it happens to be retrievable. `text_available` is
recorded per extraction so the bias can be quantified rather than assumed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# --- the schema the model must emit ----------------------------------------

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["relations", "claims", "framing"],
    "properties": {
        # What GKG cannot give us: who did what to whom.
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["subject", "predicate", "object", "confidence"],
                "properties": {
                    "subject":   {"type": "string"},
                    "predicate": {"type": "string",
                                  "description": "controlled verb, see RELATION_PREDICATES"},
                    "object":    {"type": "string"},
                    "location":  {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        # The unit UC-N2 verifies against ACLED/UCDP ground truth.
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "claim_type", "confidence"],
                "properties": {
                    "text":       {"type": "string", "maxLength": 400},
                    "claim_type": {"type": "string", "enum": [
                        "casualty", "abduction", "displacement", "attack",
                        "protest", "arrest", "statement", "other"]},
                    "date_mentioned": {"type": ["string", "null"],
                                       "description": "ISO date if stated, else null"},
                    "location":   {"type": ["string", "null"]},
                    "magnitude":  {"type": ["number", "null"],
                                   "description": "count asserted, e.g. 276 abducted"},
                    "magnitude_unit": {"type": ["string", "null"]},
                    "actor":      {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        # Refines As (UC5). GDELT tone is document-level; this is about stance.
        "framing": {
            "type": "object",
            "required": ["stance", "salience"],
            "properties": {
                "stance":   {"type": "string", "enum": [
                    "alarmed", "critical", "neutral", "reassuring", "celebratory"]},
                "salience": {"type": "number", "minimum": 0, "maximum": 1,
                             "description": "how central the conflict subject is to the record"},
                "attributed_responsibility": {"type": ["string", "null"]},
            },
        },
    },
}

# A closed set, deliberately. Free-form predicates would make the graph
# unqueryable — UC-N2 matches claims to events on actor/event type, which only
# works if the vocabulary is bounded.
RELATION_PREDICATES = [
    "attacked", "abducted", "killed", "displaced", "arrested", "protested_against",
    "condemned", "claimed_responsibility", "denied", "deployed_to", "negotiated_with",
    "rescued", "reported_on",
]

CLAIM_TYPES = ["casualty", "abduction", "displacement", "attack",
               "protest", "arrest", "statement", "other"]


# --- prompt -----------------------------------------------------------------

SYSTEM_PROMPT = """You extract structured facts from news metadata for a conflict-monitoring research system.

You are given a GDELT Global Knowledge Graph record. Entities have ALREADY been
extracted by GDELT — do not repeat them. Your task is what GDELT does not do:
identify RELATIONS between actors, and DISCRETE CLAIMS that can be checked
against event databases.

Rules:
- Use only the supplied record. Do not add knowledge from training data.
- If the record does not support a relation or claim, return an empty list.
  An empty extraction is a correct answer and is preferred to a guess.
- predicate must come from the supplied controlled vocabulary.
- magnitude is a number ONLY when the record asserts one. Never estimate.
- confidence reflects support in THIS record, not your general belief.
- Do not judge whether a claim is true. Verification happens downstream against
  ground-truth event data; your job is to state what is asserted.

Return a single JSON object matching the supplied schema and nothing else."""


def build_prompt(record: dict[str, Any], article_text: str | None = None) -> str:
    """Render one GKG record into the extraction prompt."""
    parts = [
        "GDELT GKG RECORD",
        f"date: {record.get('event_date')}",
        f"articles represented: {record.get('numarts')}",
        f"themes: {', '.join(record.get('themes', [])[:40])}",
        f"persons: {', '.join(record.get('persons', [])[:25])}",
        f"organizations: {', '.join(record.get('organizations', [])[:25])}",
        f"locations: {', '.join(record.get('locations', [])[:20])}",
        f"tone: {json.dumps(record.get('tone', {}))}",
    ]
    if article_text:
        parts += ["", "ARTICLE TEXT (available for this record):",
                  article_text[:6000]]
    else:
        parts += ["", "ARTICLE TEXT: not available — extract from metadata only."]
    parts += ["", "CONTROLLED PREDICATES: " + ", ".join(RELATION_PREDICATES),
              "CLAIM TYPES: " + ", ".join(CLAIM_TYPES),
              "", "SCHEMA:", json.dumps(EXTRACTION_SCHEMA)]
    return "\n".join(parts)


def prompt_fingerprint(system: str = SYSTEM_PROMPT) -> str:
    """
    Recorded with every extraction. UC-N1 requires prompts, model version and
    confidence to be logged as methodological artifacts; a prompt that changed
    mid-run without being noticed would silently split the corpus in two.
    """
    return hashlib.sha256((system + json.dumps(EXTRACTION_SCHEMA, sort_keys=True)).encode()).hexdigest()


def validate(payload: dict[str, Any]) -> list[str]:
    """Structural check before anything reaches the graph. Returns problems."""
    problems: list[str] = []
    for key in ("relations", "claims", "framing"):
        if key not in payload:
            problems.append(f"missing '{key}'")

    for i, rel in enumerate(payload.get("relations", []) or []):
        if rel.get("predicate") not in RELATION_PREDICATES:
            problems.append(f"relations[{i}]: predicate '{rel.get('predicate')}' outside vocabulary")
        c = rel.get("confidence")
        if not isinstance(c, (int, float)) or not 0 <= c <= 1:
            problems.append(f"relations[{i}]: confidence not in [0,1]")

    for i, cl in enumerate(payload.get("claims", []) or []):
        if cl.get("claim_type") not in CLAIM_TYPES:
            problems.append(f"claims[{i}]: claim_type '{cl.get('claim_type')}' outside vocabulary")
        mag = cl.get("magnitude")
        if mag is not None and not isinstance(mag, (int, float)):
            problems.append(f"claims[{i}]: magnitude must be a number or null")

    framing = payload.get("framing") or {}
    if framing and framing.get("stance") not in (
            "alarmed", "critical", "neutral", "reassuring", "celebratory"):
        problems.append(f"framing: stance '{framing.get('stance')}' outside vocabulary")
    return problems


# Persisted alongside every extraction, per UC-N1's methodological-artifact
# requirement. text_available is what makes the source bias measurable.
EXTRACTION_PROVENANCE_FIELDS = [
    "model_name", "model_version", "prompt_sha256", "schema_version",
    "text_available", "extracted_at", "validation_problems",
]

SCHEMA_VERSION = "1.0"
