"""
Thesis constructs measured against GDELT (Forteta 2026).

Four families, each tied to a specific construct in the thesis:

  CVD            Colonial Variety Deficit, J = |G_O n G_S| / |G_O u G_S|
                 (Ch.3 s3.5.4; bands >=0.4 viable, 0.2-0.4 marginal, <0.2 critical)
  Forgetting     the four modes of Infrastructural Forgetting, of which two are
                 observable in a media archive
  Algedonic      the Algedonic Signal Deficit (s5.5) — lead time and alarm rate
  Cynefin        System D's three-pathway routing architecture (s4.3.2)

Two of these are direct applications of the thesis's own instruments. Two are
proposed operationalisations, marked as such below, and should not be read as
the thesis's definitions.
"""
from __future__ import annotations

import json
from statistics import mean, pstdev
from typing import Any

from . import rolling, store

# ---------------------------------------------------------------------------
# 1. CVD — direct application of the thesis protocol
# ---------------------------------------------------------------------------

VIABLE, MARGINAL = 0.4, 0.2


def band(j: float) -> str:
    return "viable" if j >= VIABLE else ("marginal" if j >= MARGINAL else "critical")


def cvd_jaccard(need: set[str], detected: set[str],
                alarms_total: int) -> dict[str, Any]:
    """
    J(detection need, actual detection), on the thesis's set-theoretic protocol.

    The mapping to G_O / G_S is exact in structure:

        G_O n G_S   designed function operationally present   -> crisis detected
        G_O \\ G_S   designed but absent (the deficit)          -> crisis missed
        G_S \\ G_O   shadow workflows                           -> unexplained alarms

    The third row is why unexplained alarms belong in the union rather than
    being discarded as error: in the thesis they are the shadow systems the
    Workshop Communique resolves to harvest as "Survival Strategies", and under
    System D's Cynefin routing they are Confused-domain signals requiring
    reflexive audit. Both framings treat them as diagnostic, not noise.

    **J here is an upper bound.** Only six Nigerian crises can be enumerated
    without ACLED; true need is larger and J falls monotonically as it grows.
    """
    hit = need & detected
    union = len(need) + alarms_total - len(hit)
    j = len(hit) / union if union else None
    return {
        "need": len(need), "alarms": alarms_total,
        "intersection": len(hit), "missed": len(need - detected),
        "unexplained": alarms_total - len(hit),
        "union": union, "J": round(j, 4) if j is not None else None,
        "band": band(j) if j is not None else None,
        "gap_pct": round(100 * (1 - j), 1) if j is not None else None,
        "bound": "upper — true need is larger than the enumerable six",
    }


def cvd_by_class(need_by_class: dict[str, set[str]],
                 detected: set[str]) -> dict[str, Any]:
    """
    Coverage of need, decomposed by crisis class.

    Labelled honestly: alarms cannot be assigned to a crisis class, so the union
    term drops out and these are **coverage ratios**, not Jaccard coefficients.
    They are reported beside J because the decomposition is where the finding
    lives — the deficit is partitioned, not diffuse.
    """
    out = {}
    for name, need in need_by_class.items():
        c = len(need & detected) / len(need) if need else None
        out[name] = {"need": len(need), "covered": len(need & detected),
                     "coverage": round(c, 4) if c is not None else None,
                     "band": band(c) if c is not None else None}
    return out


# ---------------------------------------------------------------------------
# 2. Infrastructural Forgetting — two of four modes are observable here
# ---------------------------------------------------------------------------

def structural_forgetting(counts: dict[str, dict[str, float]]) -> dict[str, Any]:
    """
    Structural Forgetting (TIF mode 4, VSM S4/S5): "loss of contextual linkages
    ... during system migrations, producing archival discontinuity that severs
    the institution from its own operational past."

    Measured on the archive itself. If the density of the record is not
    stationary, the past is thinner than the present *as maintained*, which is
    forgetting by maintenance rather than by decay.
    """
    by_year: dict[str, list[float]] = {}
    for day, v in counts.items():
        by_year.setdefault(day[:4], []).append(v["total_events"])
    years = sorted(by_year)
    means = {y: mean(by_year[y]) for y in years}
    peak_y = max(means, key=means.get)
    base_y = min(means, key=means.get)
    return {
        "by_year": {y: round(means[y], 1) for y in years},
        "peak_year": peak_y, "peak": round(means[peak_y], 1),
        "trough_year": base_y, "trough": round(means[base_y], 1),
        "ratio_peak_to_trough": round(means[peak_y] / means[base_y], 3),
        "coefficient_of_variation": round(
            pstdev(list(means.values())) / mean(list(means.values())), 4),
        "reading": ("Archive density is non-stationary. A record whose past is "
                    "systematically thinner than its present exhibits Structural "
                    "Forgetting as a property of maintenance, not decay."),
    }


def epistemic_forgetting(case_id: int, platform: str = "gdelt_gkg") -> dict[str, Any]:
    """
    Epistemic Forgetting (TIF mode 3, VSM S3): "the exclusion of alternative
    epistemologies — narrative, experiential, vernacular, and indigenous — in
    favour of metrics-driven governance logics."

    Two measurements, both about whose testimony the archive can hold:

    1. **Source concentration** (Herfindahl-Hirschman). A concentrated archive
       records fewer distinct voices regardless of volume.
    2. **Trust ceiling.** Manara ranks traditional leaders 8-10 and family
       elders 7-9; media 3-5. GDELT is entirely media, so the proportion of the
       corpus above Ts=5 is structurally zero. The transmitters carrying the
       most epistemic authority in the construct are invisible to the
       instrument — which is Epistemic Forgetting measured directly, in the
       sensing layer rather than the records layer.
    """
    from .manara import domains_of, source_trust
    from collections import Counter

    dom = Counter()
    with store.db() as conn:
        for r in conn.execute(
                "SELECT raw_json FROM records WHERE case_id=? AND source_platform=?",
                (case_id, platform)):
            for d in domains_of(json.loads(r["raw_json"])):
                dom[d] += 1
    total = sum(dom.values())
    if not total:
        return {"observable": False}

    shares = [n / total for n in dom.values()]
    hhi = sum(s * s for s in shares)
    top10 = sum(n for _, n in dom.most_common(10)) / total
    above5 = sum(n for d, n in dom.items() if source_trust(d) > 5.0) / total
    return {
        "observable": True,
        "distinct_domains": len(dom), "url_mentions": total,
        "hhi": round(hhi, 5),
        "top10_share": round(top10, 4),
        "share_above_media_band": round(above5, 6),
        "reading": ("Share above the media trust band is structurally zero: the "
                    "high-trust transmitters in Manara's ranking — traditional "
                    "leaders, family elders, ritual occasions — cannot appear in "
                    "a news archive at all."),
    }


# ---------------------------------------------------------------------------
# 3. Algedonic Signal Deficit — thesis s5.5
# ---------------------------------------------------------------------------

def algedonic(series: dict[str, float], triggers: list[str], k: float = 2.0,
              persistence: int = 3, max_lead: int = 28) -> dict[str, Any]:
    """
    The algedonic channel's operating characteristics.

    The thesis specifies the Chaotic -> S5 bypass architecturally but not
    quantitatively. An override that fires too often is attenuated by the
    management layer exactly as the informal channels already are; one that
    never fires leaves the deficit in place. Alarm rate is therefore a design
    parameter, not a diagnostic afterthought.
    """
    from datetime import datetime

    def _d(s): return datetime.strptime(s, "%Y-%m-%d").date()

    alarms = rolling.rolling_alarms(series, k=k, persistence=persistence)
    days = sorted(series)
    observed = len(days) - rolling.BASELINE_WINDOW
    years = observed / 365.25

    hits = {}
    explained = set()
    for t in triggers:
        td = _d(t)
        m = [a for a in alarms if 0 < (td - _d(a["day"])).days <= max_lead]
        if m:
            hits[t] = max((td - _d(a["day"])).days for a in m)
            explained.update(a["day"] for a in m)

    return {
        "alarms": len(alarms), "years": round(years, 2),
        "alarms_per_year": round(len(alarms) / years, 3) if years else None,
        "triggers": len(triggers), "hits": hits,
        "unexplained": len(alarms) - len(explained),
        "alarm_days": [a["day"] for a in alarms],
    }


# ---------------------------------------------------------------------------
# 4. Cynefin routing — PROPOSED operationalisation, not the thesis's
# ---------------------------------------------------------------------------

CYNEFIN_ROUTE = {
    "clear": "S3 standard", "complicated": "S4 technical diagnosis",
    "complex": "System D reflexive audit", "chaotic": "S5 algedonic bypass",
    "confused": "BOTH S5 alert and System D audit",
}


def cynefin_classify(day: str, z: dict[str, float]) -> str:
    """
    Classify one day's signal state into a Cynefin domain.

    **This operationalisation is proposed here, not taken from the thesis**,
    which specifies the routing architecture but not a classifier. The rules
    follow the domains' definitions:

      chaotic      extreme departure demanding immediate action (|z| > 3)
      confused     channels contradict each other — protest rising while coded
                   conflict intensity also rises toward cooperation. The thesis
                   treats inability to classify as itself a governance
                   emergency, routed to BOTH pathways.
      complex      elevated, direction not determinable (1.5 < z <= 3)
      complicated  elevated within known range (0.5 < z <= 1.5)
      clear        at baseline
    """
    zp = z.get("protest", 0.0)
    zg = z.get("goldstein", 0.0)

    if abs(zp) > 3.0:
        return "chaotic"
    # Contradiction: mobilisation up while coded conflict moves the other way.
    if zp > 1.5 and zg > 1.5:
        return "confused"
    if zp > 1.5:
        return "complex"
    if zp > 0.5:
        return "complicated"
    return "clear"


def cynefin_profile(protest: dict[str, float], goldstein: dict[str, float],
                    window: int = 28) -> dict[str, Any]:
    """Route every day in the series and report the distribution."""
    days = sorted(set(protest) & set(goldstein))
    counts = {k: 0 for k in CYNEFIN_ROUTE}
    per_day: dict[str, str] = {}
    for i in range(window, len(days)):
        z = {}
        for name, s in (("protest", protest), ("goldstein", goldstein)):
            base = [s[d] for d in days[i - window:i]]
            mu, sd = mean(base), pstdev(base)
            z[name] = (s[days[i]] - mu) / sd if sd else 0.0
        dom = cynefin_classify(days[i], z)
        per_day[days[i]] = dom
        counts[dom] += 1
    total = sum(counts.values()) or 1
    return {
        "counts": counts,
        "shares": {k: round(v / total, 4) for k, v in counts.items()},
        "routes": CYNEFIN_ROUTE,
        "per_day": per_day,
        "observed_days": total,
        "note": "Classifier proposed here; the thesis specifies routing, not rules.",
    }
