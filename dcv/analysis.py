"""
Signal detection and the narrative/structural contrast (UC6).

Two series per case, measured over the same 76-day window:

  narrative  — daily GKG record volume (what was being said)
  structural — daily GDELT Events statistics for Nigeria: volume, mean
               Goldstein conflict intensity, material-conflict share, and
               protest-event share (what was coded to have happened)

The question UC6 asks is not "did the series rise" — after a mass-casualty
event everything rises. It is whether the series crossed a detection threshold
**before** the ground-truth trigger, at a lead time fixed in advance
(`parameters.LEAD_TIME_DAYS`, fixed 2026-09-15 before any of this ran).

Detection rule, stated before use: a baseline is taken from the first 28 days of
the window; the series fires on the first day it exceeds baseline mean + k·SD
for `persistence` consecutive days. k and persistence are swept rather than
tuned to a result, so the reader can see the whole surface instead of the one
cell that flatters the hypothesis.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from statistics import mean, pstdev
from typing import Any

from . import parameters, store

BASELINE_DAYS = 28


def _d(iso: str) -> date:
    return datetime.strptime(iso, "%Y-%m-%d").date()


# --------------------------------------------------------------------------
# Series construction
# --------------------------------------------------------------------------

def narrative_series(case_id: int, terms: list[str] | None = None,
                     platform: str = "gdelt_gkg") -> dict[str, float]:
    """
    Daily narrative attention.

    With `terms`, this is the keyword-filtered series the sweep established —
    the case's approved keyword set, matched on word boundaries (a bare
    substring match put "SARS" inside "ENDSARS" and silently collapsed two
    candidate sets into one). Without terms it is raw corpus volume, which is
    the ingest's Nigeria baseline and NOT a measure of attention to the case:
    the two differ by an order of magnitude and must not be conflated.
    """
    with store.db() as conn:
        rows = conn.execute(
            "SELECT event_date, content_summary, location, raw_json FROM records"
            " WHERE case_id=? AND source_platform=? AND event_date IS NOT NULL",
            (case_id, platform)).fetchall()

    if not terms:
        counts: dict[str, float] = {}
        for r in rows:
            counts[r["event_date"]] = counts.get(r["event_date"], 0.0) + 1
        return dict(sorted(counts.items()))

    pats = [re.compile(r"(?<![a-z0-9])" + re.escape(t.lower()) + r"(?![a-z0-9])")
            for t in terms]
    counts = {}
    for r in rows:
        hay = " ".join(filter(None, (r["content_summary"], r["location"],
                                     r["raw_json"]))).lower()
        if any(p.search(hay) for p in pats):
            counts[r["event_date"]] = counts.get(r["event_date"], 0.0) + 1
    # Days with no matching record are real zeros, not missing data — the
    # Chibok series is mostly zeros before the abduction, and dropping them
    # would erase exactly the fact the case is about.
    for r in rows:
        counts.setdefault(r["event_date"], 0.0)
    return dict(sorted(counts.items()))


def structural_series(case_id: int) -> dict[str, dict[str, float]]:
    """
    Daily GDELT Events statistics.

    Goldstein is averaged *weighted by NumMentions*: an unweighted mean treats a
    single-mention wire brief and a thousand-mention massacre as equal
    observations of the day's conflict intensity, which is not what the scale
    is for.
    """
    with store.db() as conn:
        rows = conn.execute(
            "SELECT event_date, raw_json, tone_score FROM records"
            " WHERE case_id=? AND source_platform='gdelt_events'"
            " AND event_date IS NOT NULL", (case_id,)).fetchall()

    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        raw = json.loads(r["raw_json"])
        d = agg.setdefault(r["event_date"], {
            "n": 0, "gold_num": 0.0, "gold_den": 0.0,
            "conflict": 0, "protest": 0, "tone_sum": 0.0, "tone_n": 0})
        d["n"] += 1
        g, mentions = raw.get("goldstein"), raw.get("num_mentions") or 1
        if g is not None:
            d["gold_num"] += g * mentions
            d["gold_den"] += mentions
        if raw.get("quad_class") == 4:
            d["conflict"] += 1
        if raw.get("event_root_code") == "14":
            d["protest"] += 1
        if r["tone_score"] is not None:
            d["tone_sum"] += r["tone_score"]
            d["tone_n"] += 1

    out: dict[str, dict[str, float]] = {}
    for day, d in sorted(agg.items()):
        out[day] = {
            "events": float(d["n"]),
            "goldstein": round(d["gold_num"] / d["gold_den"], 4) if d["gold_den"] else None,
            "conflict_share": round(d["conflict"] / d["n"], 4) if d["n"] else None,
            "protest_events": float(d["protest"]),
            "protest_share": round(d["protest"] / d["n"], 4) if d["n"] else None,
            "tone": round(d["tone_sum"] / d["tone_n"], 4) if d["tone_n"] else None,
        }
    return out


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def detect(series: dict[str, float], trigger: str, k: float = 2.0,
           persistence: int = 2, direction: str = "up") -> dict[str, Any]:
    """
    First sustained threshold crossing, and its lead time relative to `trigger`.

    Returns lead_days > 0 for a crossing BEFORE the trigger (a genuine early
    warning), <= 0 for one on or after it (a detection of the event itself,
    which is not early warning and is reported as such).
    """
    days = sorted(d for d in series if series[d] is not None)
    if len(days) < BASELINE_DAYS + 5:
        return {"fired": False, "reason": "insufficient series length"}

    base = [series[d] for d in days[:BASELINE_DAYS]]
    mu, sd = mean(base), pstdev(base)
    if sd == 0:
        return {"fired": False, "reason": "zero-variance baseline"}
    thresh = mu + k * sd if direction == "up" else mu - k * sd

    run = 0
    for d in days[BASELINE_DAYS:]:
        v = series[d]
        over = v > thresh if direction == "up" else v < thresh
        run = run + 1 if over else 0
        if run >= persistence:
            first = days[days.index(d) - persistence + 1]
            return {
                "fired": True, "crossed_on": first,
                "lead_days": (_d(trigger) - _d(first)).days,
                "threshold": round(thresh, 4),
                "baseline_mean": round(mu, 4), "baseline_sd": round(sd, 4),
                "value_at_cross": round(series[first], 4),
            }
    return {"fired": False, "reason": "never crossed",
            "threshold": round(thresh, 4), "baseline_mean": round(mu, 4),
            "baseline_sd": round(sd, 4)}


def detection_surface(series: dict[str, float], trigger: str,
                      ks=(1.5, 2.0, 2.5, 3.0),
                      persistences=(1, 2, 3)) -> list[dict[str, Any]]:
    """
    Sweep the detection rule instead of picking one.

    A single (k, persistence) pair that happens to produce a positive lead time
    proves nothing; what matters is whether early detection survives across the
    parameter surface, or exists only in one corner of it.
    """
    out = []
    for k in ks:
        for p in persistences:
            r = detect(series, trigger, k=k, persistence=p)
            out.append({"k": k, "persistence": p, **r})
    return out


# --------------------------------------------------------------------------
# Pre-trigger trend — the sweep's metric, reused so the two are comparable
# --------------------------------------------------------------------------

def pre_trigger_trend(series: dict[str, float], trigger: str) -> dict[str, Any]:
    pre = [series[d] for d in sorted(series) if d < trigger and series[d] is not None]
    post = [series[d] for d in sorted(series) if d >= trigger and series[d] is not None]
    if not pre:
        return {"n_pre": 0}
    half = len(pre) // 2
    early, late = pre[:half], pre[half:]
    return {
        "n_pre": len(pre), "n_post": len(post),
        "pre_mean": round(mean(pre), 3),
        "post_mean": round(mean(post), 3) if post else None,
        "pre_sd": round(pstdev(pre), 3) if len(pre) > 1 else None,
        "early_mean": round(mean(early), 3) if early else None,
        "late_mean": round(mean(late), 3) if late else None,
        # Ratio is the sweep's metric and is kept for comparability, but it is
        # only interpretable on a non-negative series. Goldstein is signed and
        # sits near zero, so a ratio of two negatives inverts its meaning and
        # explodes near the crossing. `trend_diff` is the honest statistic for
        # any signed channel; both are reported so neither can be cherry-picked.
        "trend": round(mean(late) / mean(early), 3) if early and mean(early) else None,
        "trend_diff": round(mean(late) - mean(early), 4) if early and late else None,
        "post_over_pre": round(mean(post) / mean(pre), 3) if post and mean(pre) else None,
        "post_minus_pre": round(mean(post) - mean(pre), 4) if post else None,
    }


# --------------------------------------------------------------------------
# Per-case roll-up
# --------------------------------------------------------------------------

def analyse(case_slug: str) -> dict[str, Any]:
    case = store.get_case(case_slug)
    if case is None:
        raise ValueError(f"unknown case: {case_slug}")
    trigger = min(json.loads(case["trigger_dates"]))

    terms = json.loads(case["keywords_json"])
    # Spec comes from the newest version; records come from whichever version
    # owns them. A keyword repair creates a new spec version without re-ingesting.
    data_id = store.data_case_id(case_slug)
    struct = structural_series(data_id)

    channels: dict[str, dict[str, float]] = {
        # The case-specific attention series (approved keyword set)...
        "narrative_keyword": narrative_series(data_id, terms),
        # ...and the whole-corpus Nigeria baseline it must be read against.
        "narrative_corpus": narrative_series(data_id),
    }
    for metric in ("events", "goldstein", "conflict_share", "protest_events",
                   "protest_share", "tone"):
        channels[f"structural_{metric}"] = {
            d: v[metric] for d, v in struct.items() if v[metric] is not None}

    result: dict[str, Any] = {
        "case": case_slug, "trigger": trigger,
        "model_direction": case["model_direction"],
        "keywords": terms,
        "spec_case_id": case["case_id"],
        "data_case_id": data_id,
        "spec_version": case["version"],
        "keywords_status": case["keywords_status"],
        "lead_time_target_days": parameters.LEAD_TIME_DAYS.get(case_slug),
        "parameters_version": parameters.PARAMETERS_VERSION,
        "channels": {},
    }

    for name, s in channels.items():
        if len(s) < BASELINE_DAYS + 5:
            result["channels"][name] = {"n_days": len(s), "note": "series too short"}
            continue
        # Goldstein falls as conflict intensifies, so it is detected downward.
        direction = "down" if name.endswith("goldstein") else "up"
        result["channels"][name] = {
            "n_days": len(s),
            "trend": pre_trigger_trend(s, trigger),
            "detection": detect(s, trigger, k=2.0, persistence=2, direction=direction),
            "surface": detection_surface(s, trigger),
            "series": dict(sorted(s.items())),
        }
    return result


def report(res: dict[str, Any]) -> str:
    L = [
        f"  case             : {res['case']}   (Model {res['model_direction']})",
        f"  trigger          : {res['trigger']}",
        f"  lead-time target : {res['lead_time_target_days']} days"
        f"   [parameters v{res['parameters_version']}]",
        "",
        f"  {'channel':<28}{'days':>6}{'pre':>10}{'post':>10}{'trend':>8}"
        f"{'Δtrend':>9}{'fires':>7}{'lead':>7}",
        "  " + "-" * 85,
    ]
    for name, c in res["channels"].items():
        if "note" in c:
            L.append(f"  {name:<28}{c['n_days']:>6}   {c['note']}")
            continue
        t, d = c["trend"], c["detection"]
        pre = t["pre_mean"]
        post = t["post_mean"] if t["post_mean"] is not None else 0
        fires = "yes" if d.get("fired") else "no"
        lead = d.get("lead_days")
        lead_s = f"{lead:+d}" if lead is not None else "--"
        L.append(f"  {name:<28}{c['n_days']:>6}{pre:>10.3f}{post:>10.3f}"
                 f"{(t['trend'] or 0):>8.2f}{(t['trend_diff'] or 0):>9.3f}"
                 f"{fires:>7}{lead_s:>7}")
    L += [
        "",
        "  trend = later-half / earlier-half of the PRE-trigger window (ratio).",
        "  Δtrend = later-half minus earlier-half. Use Δtrend for goldstein and",
        "          tone: a ratio of two negatives inverts on a signed scale.",
        "  lead  = days between first sustained crossing and the trigger;",
        "          positive is early warning, negative is after-the-fact detection.",
    ]
    return "\n".join(L)
