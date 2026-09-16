"""
Prospective (rolling-baseline) detection.

The detector in `analysis.detect` takes its baseline from the first 28 days of a
window that was drawn around a trigger date we already knew. That is fine for
asking "was there a signal", and useless for asking "would this have fired in
operation", because in operation there is no window — only a running series and
a decision to make today.

This module removes that advantage. At each day t the baseline is the trailing
`window` days ending at t-1; the threshold is recomputed every day; and the
detector has no knowledge of where the trigger falls. Everything it sees, an
operator standing on day t would also have seen.

Two quantities come out, and the second is the one that matters:

  lead        — days between the first firing before the trigger and the trigger
  alarm rate  — how often the detector fires at all, per 100 days

A channel that fires 10 days before a crisis is worthless if it also fires every
fortnight. Lead time without an alarm rate is not evidence of early warning; it
is evidence that the detector fires, which we already knew.
"""
from __future__ import annotations

from datetime import date, datetime
from statistics import mean, pstdev
from typing import Any

BASELINE_WINDOW = 28
REFRACTORY_DAYS = 14          # an alarm suppresses re-alarms for this long


def _d(iso: str) -> date:
    return datetime.strptime(iso, "%Y-%m-%d").date()


def rolling_alarms(series: dict[str, float], k: float = 2.0,
                   persistence: int = 2, window: int = BASELINE_WINDOW,
                   refractory: int = REFRACTORY_DAYS,
                   direction: str = "up") -> list[dict[str, Any]]:
    """
    Every day the detector would have fired, using only prior data.

    A refractory period collapses one sustained episode into a single alarm.
    Without it a three-week protest wave counts as fifteen alarms and the alarm
    rate becomes a measure of episode length rather than of how often an
    operator is interrupted.
    """
    days = sorted(d for d in series if series[d] is not None)
    alarms: list[dict[str, Any]] = []
    run = 0
    last_alarm: date | None = None

    for i in range(window, len(days)):
        base = [series[d] for d in days[i - window:i]]
        mu, sd = mean(base), pstdev(base)
        if sd == 0:
            run = 0
            continue
        thresh = mu + k * sd if direction == "up" else mu - k * sd
        v = series[days[i]]
        over = v > thresh if direction == "up" else v < thresh
        run = run + 1 if over else 0
        if run >= persistence:
            day = _d(days[i - persistence + 1])
            if last_alarm is not None and (day - last_alarm).days < refractory:
                continue
            last_alarm = day
            alarms.append({
                "day": day.isoformat(), "value": round(v, 4),
                "threshold": round(thresh, 4), "baseline_mean": round(mu, 4),
                "baseline_sd": round(sd, 4),
            })
    return alarms


def evaluate(series: dict[str, float], trigger: str, k: float = 2.0,
             persistence: int = 2, window: int = BASELINE_WINDOW,
             max_lead: int = 28, direction: str = "up") -> dict[str, Any]:
    """
    Prospective performance on one case.

    `hit` requires an alarm in the (0, max_lead] days before the trigger — an
    alarm 60 days out is not a warning about this event, and counting it as one
    is how retrospective analyses manufacture lead time.
    """
    days = sorted(d for d in series if series[d] is not None)
    if len(days) < window + 5:
        return {"evaluable": False, "reason": "series shorter than baseline window"}

    alarms = rolling_alarms(series, k, persistence, window, direction=direction)
    t = _d(trigger)
    scored = [{**a, "days_before_trigger": (t - _d(a["day"])).days} for a in alarms]

    in_lead = [a for a in scored if 0 < a["days_before_trigger"] <= max_lead]
    early_useless = [a for a in scored if a["days_before_trigger"] > max_lead]
    after = [a for a in scored if a["days_before_trigger"] <= 0]

    observed = len(days) - window          # days the detector could actually fire
    return {
        "evaluable": True,
        "observed_days": observed,
        "alarms_total": len(scored),
        "alarm_rate_per_100d": round(100 * len(scored) / observed, 2) if observed else None,
        "hit": bool(in_lead),
        "lead_days": max(a["days_before_trigger"] for a in in_lead) if in_lead else None,
        "alarms_in_lead_window": len(in_lead),
        "alarms_too_early": len(early_useless),
        "alarms_after_trigger": len(after),
        "alarms": scored,
    }
