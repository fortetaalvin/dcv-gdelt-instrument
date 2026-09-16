"""
Keyword sensitivity sweep (SAD Open Item 4).

The query set determines the corpus and therefore every downstream figure, so
the SAD requires it to be fixed before analysis rather than chosen post hoc.
This module makes that choice evidential: run several candidate sets over the
same ingested corpus, show what each includes and excludes, and let the
researcher pick with the consequences visible.

Design note: candidates are evaluated against ALREADY-STORED records by
re-filtering `raw_json`, never by re-querying the source. One broad ingest,
many narrow evaluations. That keeps the comparison honest — every candidate
sees exactly the same underlying corpus — and avoids hammering GDELT.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from statistics import mean, pstdev
from typing import Any

from . import store


def _daily_counts(case_id: int, terms: list[str], platform: str) -> dict[str, int]:
    """
    Records per day whose stored payload matches any term.

    Word-boundary matching, not substring. Naive substring matching made the
    SARS/COVID collision test meaningless, because "SARS" is contained in
    "ENDSARS" — the candidate that was supposed to measure COVID contamination
    was silently matching the protest hashtag and returned numbers identical to
    the hashtag candidate. Any acronym that is a substring of another term has
    the same problem.
    """
    pats = [re.compile(r"(?<![a-z0-9])" + re.escape(t.lower()) + r"(?![a-z0-9])")
            for t in terms]
    counts: dict[str, int] = {}
    with store.db() as conn:
        rows = conn.execute(
            "SELECT event_date, content_summary, location, raw_json FROM records"
            " WHERE case_id=? AND source_platform=? AND event_date IS NOT NULL",
            (case_id, platform),
        ).fetchall()
    for r in rows:
        hay = " ".join(filter(None, (r["content_summary"], r["location"], r["raw_json"]))).lower()
        if any(p.search(hay) for p in pats):
            counts[r["event_date"]] = counts.get(r["event_date"], 0) + 1
    return counts


def evaluate(case_slug: str, candidates: dict[str, list[str]],
             platform: str = "gdelt_gkg") -> dict[str, Any]:
    """
    For each candidate keyword set, report corpus size and — the question that
    matters for UC6 — whether the series is elevated BEFORE the trigger date.
    """
    case = store.get_case(case_slug)
    if case is None:
        raise ValueError(f"unknown case: {case_slug}")
    triggers = json.loads(case["trigger_dates"])
    trigger = min(triggers)

    out: dict[str, Any] = {
        "case": case_slug, "trigger": trigger, "platform": platform, "candidates": {}
    }

    for name, terms in candidates.items():
        counts = _daily_counts(case["case_id"], terms, platform)
        if not counts:
            out["candidates"][name] = {"terms": terms, "total": 0, "note": "no matching records"}
            continue

        pre = [v for d, v in counts.items() if d < trigger]
        post = [v for d, v in counts.items() if d >= trigger]

        # Is the pre-trigger series flat, or already climbing? A backtest that
        # claims early warning needs movement BEFORE the trigger, not after.
        pre_sorted = [counts[d] for d in sorted(counts) if d < trigger]
        half = len(pre_sorted) // 2
        early, late = pre_sorted[:half], pre_sorted[half:]

        out["candidates"][name] = {
            "terms": terms,
            "total": sum(counts.values()),
            "days_covered": len(counts),
            "pre_mean": round(mean(pre), 1) if pre else None,
            "pre_sd": round(pstdev(pre), 1) if len(pre) > 1 else None,
            "post_mean": round(mean(post), 1) if post else None,
            "pre_ratio": round(mean(late) / mean(early), 2) if early and late and mean(early) else None,
            "post_over_pre": round(mean(post) / mean(pre), 2) if pre and post and mean(pre) else None,
            "series": dict(sorted(counts.items())),
        }
    return out


def report(result: dict[str, Any]) -> str:
    lines = [
        f"  case    : {result['case']}",
        f"  trigger : {result['trigger']}",
        f"  platform: {result['platform']}",
        "",
        f"  {'candidate':<22}{'total':>8}{'days':>6}{'pre/day':>10}{'post/day':>10}"
        f"{'post:pre':>10}{'pre trend':>11}",
        "  " + "-" * 77,
    ]
    for name, c in result["candidates"].items():
        if c.get("note"):
            lines.append(f"  {name:<22}{c['note']}")
            continue
        lines.append(
            f"  {name:<22}{c['total']:>8}{c['days_covered']:>6}"
            f"{c['pre_mean'] or 0:>10.1f}{c['post_mean'] or 0:>10.1f}"
            f"{c['post_over_pre'] or 0:>10.2f}{c['pre_ratio'] or 0:>11.2f}"
        )
    lines += [
        "",
        "  pre trend = later-half / earlier-half of the PRE-trigger window.",
        "  A value near 1.0 means the narrative was flat until the event — no",
        "  early-warning signal to detect, whatever the threshold (UC6).",
    ]
    return "\n".join(lines)


# Candidate sets for discussion. Deliberately spanning narrow-to-broad, because
# the question for Chibok is whether a *broader* framing carries pre-trigger
# signal that the place name cannot — the term "Chibok" did not exist in
# coverage until six days after the abduction.
CHIBOK_CANDIDATES = {
    "place_name_only":  ["Chibok"],
    "actor_narrow":     ["Boko Haram"],
    "actor_plus_place": ["Boko Haram", "Chibok", "Borno"],
    "regional":         ["Borno", "Yobe", "Adamawa", "Maiduguri"],
    "broad_conflict":   ["Boko Haram", "Borno", "Yobe", "Adamawa", "Maiduguri", "insurgency"],
}

ENDSARS_CANDIDATES = {
    "hashtag_only":     ["EndSARS"],
    "hashtag_plus_sars": ["EndSARS", "SARS"],
    "issue_framing":    ["police brutality", "SARS", "EndSARS"],
    "broad":            ["EndSARS", "SARS", "police brutality", "Lekki", "protest Nigeria"],
}
