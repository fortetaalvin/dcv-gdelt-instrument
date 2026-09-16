"""
TSI components (UC5).

SAD §3:  **TSI = Cw x Ts x As**

    Cw  Centrality Weight    — actor/narrative centrality in the information
                               ecosystem, via graph centrality over the
                               knowledge graph
    Ts  Trust Source         — reliability/corroboration of narrative claims,
                               from (a) ACLED/UCDP dataset divergence and
                               (b) UC-N2 claim-level verification
    As  Affective Resonance  — emotional/affective signal intensity, from GDELT
                               tone/polarity refined by LLM-extracted sentiment

## What this module will and will not compute

**As — computed, fully specified.** GDELT tone and polarity are present in every
GKG record. The "refined by LLM-extracted sentiment" half of the specification
is not applied, because UC-N1 has not been run; As here is the GDELT-only
component, and is labelled `as_gdelt` rather than `As` wherever that distinction
could matter.

**Cw — computed. Resolves SAD Open Item 1.** See the algorithm note below.

**Ts — NOT COMPUTED.** Ts requires ground truth. ACLED's edge returns HTTP 403
`cf-mitigated: challenge` to this host on every path, and UCDP GED now requires
an access token. Neither dataset has been retrieved, so neither the
divergence component nor the claim-verification component exists. There is no
defensible way to produce a number here, and a placeholder multiplied into a
headline index would contaminate every figure downstream while looking
authoritative. `Ts` returns None and `tsi()` refuses to multiply.

`ts_proxy()` offers a **substitute**, clearly named: divergence between the GKG
narrative record and the Events coded record. It is not Ts. GKG and Events are
both GDELT products sharing an upstream pipeline, so they are not independent
in the way ACLED and UCDP are, and agreement between them is partly an artifact
of common sourcing. It is reported beside Cw and As, never silently folded in.

## Open Item 1 — which centrality algorithm, and why

The SAD requires this to be "justified theoretically against DEJM's framework
meaning of centrality before implementation."

DEJM's Cw asks how central an actor or narrative is *in the information
ecosystem* — that is, how much of the ecosystem's attention flows through it.
Three candidates, against that meaning:

- **Degree centrality** counts co-occurrences. It measures volume, which As and
  the raw narrative series already measure. It would make Cw largely redundant.
- **Betweenness** measures brokerage — position on shortest paths between
  otherwise disconnected actors. Theoretically attractive, but it is O(V·E),
  unstable under the sampling noise of a daily co-occurrence graph, and its
  meaning (bridging structural holes) is a claim about *brokerage*, not about
  attention.
- **Eigenvector centrality** scores an actor by the centrality of the actors it
  co-occurs with. This is the closest match: DEJM's information ecosystem is
  recursive — being named alongside central actors is what makes an actor
  central. It is also stable on sparse daily graphs and cheap to compute.

**Chosen: eigenvector centrality**, computed by power iteration on the daily
actor co-occurrence matrix. PageRank was rejected as a variant: its damping
factor models a random surfer teleporting, which has no interpretation in a
co-occurrence graph, and would add a free parameter with no theoretical anchor.

Cw for a day is the **attention-share-weighted mean eigenvector centrality of
the case's focal actors** — i.e. how central the actors this case is about were
in that day's information ecosystem. A day where the focal actors are absent
scores 0, which is the correct reading of narrative silence.
"""
from __future__ import annotations

import json
import math
from statistics import mean
from typing import Any

from . import store

# Power-iteration settings. Tolerance is well below the between-day variation
# we care about, so convergence is not a source of reported difference.
MAX_ITER = 100
TOL = 1e-9


# --------------------------------------------------------------------------
# Cw — eigenvector centrality over daily actor co-occurrence
# --------------------------------------------------------------------------

def _daily_entities(case_id: int) -> dict[str, list[list[str]]]:
    """
    Per day, the entity list of each GKG record.

    Persons and organisations only. Locations are excluded: every record in a
    Nigeria-filtered corpus mentions Nigeria, so including locations makes one
    node adjacent to everything and drives the principal eigenvector to a
    constant — Cw would then be the same number every day.
    """
    with store.db() as conn:
        rows = conn.execute(
            "SELECT event_date, raw_json FROM records"
            " WHERE case_id=? AND source_platform='gdelt_gkg'"
            " AND event_date IS NOT NULL", (case_id,)).fetchall()

    out: dict[str, list[list[str]]] = {}
    for r in rows:
        raw = json.loads(r["raw_json"])
        ents = set()
        for key in ("persons", "organizations"):
            for e in (raw.get(key) or []):
                e = (e or "").strip().lower()
                if len(e) > 2:
                    ents.add(e)
        if ents:
            out.setdefault(r["event_date"], []).append(sorted(ents))
    return out


def eigenvector_centrality(records: list[list[str]],
                           max_nodes: int = 400) -> dict[str, float]:
    """
    Eigenvector centrality on the co-occurrence graph of one day.

    Nodes are capped at the `max_nodes` most frequent entities. The tail of a
    daily GKG entity list is mostly one-off extraction noise, and letting it in
    both slows the iteration and adds nodes whose centrality is meaningless.
    The cap is recorded in the output so the truncation is never invisible.
    """
    freq: dict[str, int] = {}
    for ents in records:
        for e in ents:
            freq[e] = freq.get(e, 0) + 1
    if not freq:
        return {}
    nodes = sorted(freq, key=lambda e: (-freq[e], e))[:max_nodes]
    idx = {e: i for i, e in enumerate(nodes)}
    n = len(nodes)
    if n < 2:
        return {nodes[0]: 1.0} if n else {}

    # Weighted adjacency: how often two entities appear in the same record.
    adj: list[dict[int, float]] = [dict() for _ in range(n)]
    for ents in records:
        present = [idx[e] for e in ents if e in idx]
        for a in range(len(present)):
            for b in range(a + 1, len(present)):
                i, j = present[a], present[b]
                adj[i][j] = adj[i].get(j, 0.0) + 1.0
                adj[j][i] = adj[j].get(i, 0.0) + 1.0

    v = [1.0 / math.sqrt(n)] * n
    for _ in range(MAX_ITER):
        nv = [0.0] * n
        for i, row in enumerate(adj):
            s = 0.0
            for j, w in row.items():
                s += w * v[j]
            nv[i] = s
        norm = math.sqrt(sum(x * x for x in nv))
        if norm == 0:
            return {e: 0.0 for e in nodes}
        nv = [x / norm for x in nv]
        if sum(abs(nv[i] - v[i]) for i in range(n)) < TOL:
            v = nv
            break
        v = nv
    return {e: v[idx[e]] for e in nodes}


def cw_series(case_id: int, focal_terms: list[str],
              max_nodes: int = 1500) -> dict[str, dict[str, Any]]:
    """
    Daily Cw: the share of the day's principal eigenvector mass sitting on
    entities that refer to this case.

    Three decisions, each forced by something measured in the corpus:

    1. **Sum, not mean.** The eigenvector is L2-normalised, so summing the
       focal nodes' scores gives the proportion of the ecosystem's centrality
       mass attached to this case — which is exactly what "how central is this
       case in the information ecosystem" means. A mean is unstable against the
       node count: one high-ranking focal entity would outscore ten mid-ranking
       ones even though the latter collectively command more attention.

    2. **Word-boundary matching.** Substring matching put `michael jk bokor`
       into the focal set for the term "boko". This is the same failure that
       put "SARS" inside "ENDSARS" during keyword selection; it recurs wherever
       a short token is matched loosely, so it is fixed the same way.

    3. **Node cap 1500, not 400.** Focal entities in the Chibok corpus rank as
       low as 401 on a busy day, so a 400-node cap silently excluded them and
       returned Cw = 0 for days that plainly had coverage. Centrality of the
       top nodes is stable across caps (0.3889 -> 0.3915 for the top node at
       400 vs 1500), so raising it costs accuracy nothing and costs ~0.4s/day.

    Known limitation, measured rather than assumed: GKG v1 entity strings are
    verbose and fragmented. The Chibok referent appears as
    `chibok government girls secondary school` (618), `government girls
    secondary school in chibok` (343) and `chibok girls secondary school` (106)
    as three separate nodes. Cw therefore *understates* focal centrality by
    splitting one referent's mass across several nodes. Summing mitigates this
    (the fragments are all counted); it does not cure it, because co-occurrence
    edges that should point at one node are split too.
    """
    import re
    daily = _daily_entities(case_id)
    pats = [re.compile(r"(?<![a-z0-9])" + re.escape(t.lower()) + r"(?![a-z0-9])")
            for t in focal_terms]
    out: dict[str, dict[str, Any]] = {}
    for day in sorted(daily):
        cent = eigenvector_centrality(daily[day], max_nodes=max_nodes)
        hits = {e: c for e, c in cent.items() if any(p.search(e) for p in pats)}
        out[day] = {
            # Primary: share of centrality mass on this case.
            "cw": round(sum(hits.values()), 6) if hits else 0.0,
            "cw_mean": round(mean(hits.values()), 6) if hits else 0.0,
            "cw_max": round(max(hits.values()), 6) if hits else 0.0,
            "focal_nodes": len(hits),
            "graph_nodes": len(cent),
            "records": len(daily[day]),
            "truncated": len(cent) >= max_nodes,
        }
    return out


# --------------------------------------------------------------------------
# As — affective resonance from GDELT tone/polarity
# --------------------------------------------------------------------------

def as_series(case_id: int) -> dict[str, dict[str, float]]:
    """
    Daily affective resonance.

    GDELT's TONE field carries both tone (signed, positive = favourable) and
    polarity (unsigned emotional charge). DEJM's As is *intensity* of affective
    signal, not its direction, so As is built from polarity and the absolute
    magnitude of negative tone — a day of uniformly neutral coverage and a day
    of violently split coverage must not score alike.

        as_gdelt = polarity x |min(tone, 0)|

    Averaged over the day's records. The clamp on tone means favourable
    coverage contributes no resonance, which matches the construct: As is meant
    to capture affective charge around a developing crisis, not enthusiasm.
    """
    with store.db() as conn:
        rows = conn.execute(
            "SELECT event_date, raw_json FROM records"
            " WHERE case_id=? AND source_platform='gdelt_gkg'"
            " AND event_date IS NOT NULL", (case_id,)).fetchall()

    agg: dict[str, dict[str, float]] = {}
    for r in rows:
        tone = (json.loads(r["raw_json"]).get("tone") or {})
        t, pol = tone.get("tone"), tone.get("polarity")
        if t is None or pol is None:
            continue
        d = agg.setdefault(r["event_date"],
                           {"n": 0, "as_sum": 0.0, "tone_sum": 0.0, "pol_sum": 0.0})
        d["n"] += 1
        d["as_sum"] += pol * abs(min(t, 0.0))
        d["tone_sum"] += t
        d["pol_sum"] += pol

    return {day: {
        "as_gdelt": round(v["as_sum"] / v["n"], 5),
        "tone": round(v["tone_sum"] / v["n"], 4),
        "polarity": round(v["pol_sum"] / v["n"], 4),
        "n": v["n"],
    } for day, v in sorted(agg.items()) if v["n"]}


# --------------------------------------------------------------------------
# Ts — refused, and its labelled substitute
# --------------------------------------------------------------------------

def ts_series(case_id: int) -> None:
    """
    Trust Source. Returns None, deliberately.

    Ts is defined over ACLED/UCDP divergence and UC-N2 claim verification.
    Neither ground-truth source has been retrieved (ACLED edge challenge; UCDP
    token), and UC-N1 extraction has not been run. There is nothing to compute
    from. Returning None rather than a default is the point: a default would
    propagate into TSI and into the paper as an authoritative-looking figure
    with no evidential basis.
    """
    return None


def ts_proxy_series(case_id: int) -> dict[str, float]:
    """
    SUBSTITUTE for Ts, and not to be reported as Ts.

    Measures agreement between the narrative record (GKG) and the coded-event
    record (GDELT Events) on the same day, as the correlation-free ratio of
    conflict-coded activity to narrative volume, normalised to the window.

    Why this is weaker than the specified Ts: ACLED and UCDP are independently
    coded by different institutions from partly different sources, so their
    divergence carries information about reliability. GKG and Events are two
    products of one pipeline over largely the same article stream; agreement
    between them partly reflects shared upstream decisions rather than
    corroboration. Treat this as a coherence check, not a trust measure.
    """
    with store.db() as conn:
        gkg_n = dict(conn.execute(
            "SELECT event_date, COUNT(*) FROM records WHERE case_id=?"
            " AND source_platform='gdelt_gkg' AND event_date IS NOT NULL"
            " GROUP BY event_date", (case_id,)).fetchall())
        ev_rows = conn.execute(
            "SELECT event_date, raw_json FROM records WHERE case_id=?"
            " AND source_platform='gdelt_events' AND event_date IS NOT NULL",
            (case_id,)).fetchall()

    conflict: dict[str, int] = {}
    for r in ev_rows:
        if json.loads(r["raw_json"]).get("quad_class") == 4:
            conflict[r["event_date"]] = conflict.get(r["event_date"], 0) + 1

    raw = {d: conflict.get(d, 0) / n for d, n in gkg_n.items() if n}
    if not raw:
        return {}
    hi = max(raw.values()) or 1.0
    return {d: round(v / hi, 5) for d, v in sorted(raw.items())}


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def tsi(case_id: int, focal_terms: list[str]) -> dict[str, Any]:
    """
    Assemble what is computable. Refuses to emit a complete TSI.

    `tsi_partial` is Cw x As only, and is named so that no reader can mistake
    it for the three-component index the SAD specifies.
    """
    cw = cw_series(case_id, focal_terms)
    a = as_series(case_id)
    tsp = ts_proxy_series(case_id)
    ts = ts_series(case_id)

    days = sorted(set(cw) & set(a))
    partial = {d: round(cw[d]["cw"] * a[d]["as_gdelt"], 8) for d in days}

    return {
        "cw": cw, "as": a, "ts": ts, "ts_proxy": tsp,
        "tsi_partial": partial,
        "tsi_complete": None,
        "tsi_complete_reason": (
            "Ts requires ACLED/UCDP ground truth (unavailable: ACLED edge "
            "challenge, UCDP token) and UC-N2 claim verification (not run). "
            "No complete TSI is computable in this round."),
        "components_present": ["Cw", "As"],
        "components_missing": ["Ts"],
    }
