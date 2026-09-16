"""
TSI per Usman, Forteta, Bello, Bakari & Ingio (2026) — the Manara paper.

    TSI = Cw x Ts x Ar          each component on a 1-10 band, product 1-1000

This replaces an earlier implementation built from a specification that had the
construct wrong in every particular: it called the index "Total Signal Index"
(it is the **Tacit Score Index**), wrote the third term as As, and defined that
term as affective *intensity*. Ar is the paper's central theoretical
innovation and runs the other way — it is **inversely proportional to explicit
conflict language**. The earlier code computed `polarity * |min(tone,0)|`,
which is the inverse of the construct it claimed to measure.

## What each component means, and what GDELT can and cannot give

**Cw — Centrality Weight.** Paper: "how foundational a narrative is to community
identity ... calculated through network analysis of how frequently a narrative
is referenced as justification for other claims." This is *argumentative*
centrality — a premise supporting downstream assertions — not actor
co-occurrence. The closest GDELT object is the **theme** co-occurrence graph: a
theme that recurs alongside many other themes is functioning as framing context
for them. Eigenvector centrality over that graph is the proxy used here.

**Ts — Source Trust.** Paper: participant rankings. Traditional leaders 8-10,
family elders 7-9, elected officials 4-6, **media 3-5**, anonymous social 1-3.

Two consequences, both important and both reported rather than smoothed over.
First, GDELT is *entirely* media, so the whole corpus sits in the 3-5 band and Ts
contributes far less variance than it does in the Mubi fieldwork. Second, and
more consequential for the theory: the highest-trust transmitters in Manara's
scheme — traditional leaders, family elders, ritual occasions — are
**structurally invisible to GDELT**. The instrument cannot observe the sources
that carry the most weight in the construct. That is not a limitation to be
apologised for; it is a measurement of whose testimony the global news
infrastructure does not record.

**Ar — Affective Resonance.** Paper's banding, applied to linguistic features:
explicit antagonism ("they invaded", "they stole") 1-3; neutral historical
framing ("they migrated", "they settled") 4-7; heritage framing with positive
affect 8-10. GKG gives negative-word density and a conflict-theme vocabulary,
which together proxy "explicit conflict language" directly.

## The domain caveat that governs all of it

TSI was designed for **tacit weaponization inside closed trusted micro-publics**
— WhatsApp family groups, religious networks — where silence functions as assent
and quietness is the danger signal. GDELT is open public media, which the paper
itself ranks lowest on trust. Running TSI over GDELT is running a
quietness-detector across a loudness-archive. The numbers below are computed
faithfully to the formula; whether the formula belongs in this domain is a
separate question, and the answer is probably not.
"""
from __future__ import annotations

import json
import math
import re
from statistics import mean
from typing import Any
from urllib.parse import urlparse

from . import store

# --- Ts: source-trust tiers -------------------------------------------------
#
# All of GDELT sits inside Manara's "media" band (3-5). The tiers below split
# that band on editorial accountability, which is the dimension the paper's own
# ranking is tracking (named, answerable transmitters score higher). Nothing
# here can reach 6+; that range belongs to transmitters GDELT cannot see.

TS_NATIONAL_RECORD = 5.0     # named masthead, editorial accountability
TS_INTERNATIONAL   = 5.0     # wire services and major international desks
TS_AGGREGATOR      = 4.0     # republishes others' reporting under its own domain
TS_SYNDICATION     = 3.0     # content mills with no local desk
TS_UNKNOWN         = 3.5     # unclassified media — band midpoint

NIGERIAN_RECORD = {
    "punchng.com", "vanguardngr.com", "thisdaylive.com", "guardian.ng",
    "premiumtimesng.com", "dailytrust.com", "thenationonlineng.net",
    "tribuneonlineng.com", "thecable.ng", "businessday.ng", "sunnewsonline.com",
    "leadership.ng", "blueprint.ng", "independent.ng", "nigerianpilot.com",
    "dailypost.ng", "pulse.ng", "today.ng", "legit.ng", "channelstv.com",
}
INTERNATIONAL = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "aljazeera.com",
    "theguardian.com", "nytimes.com", "washingtonpost.com", "cnn.com",
    "france24.com", "dw.com", "voanews.com", "ft.com", "economist.com",
    "afp.com", "npr.org", "abcnews.go.com", "cbsnews.com",
}
AGGREGATOR = {
    "allafrica.com", "msn.com", "news.google.com", "yahoo.com", "news2.onlinenigeria.com",
    "onlinenigeria.com", "naija247news.com", "nigerianewsdirect.com", "newsbreak.com",
}
# Domains that surface at volume in Nigerian coverage while carrying US city
# names and no Nigerian desk. Syndication mills, not reporting.
SYNDICATION_HINT = re.compile(
    r"(texasguardian|newyorktelegraph|sandiegosun|thestreetjournal|marketwatch"
    r"|bignewsnetwork|menafn|einnews|streetinsider|benzinga)", re.I)


def source_trust(domain: str) -> float:
    d = (domain or "").lower().replace("www.", "")
    if not d:
        return TS_UNKNOWN
    if d in NIGERIAN_RECORD or d in INTERNATIONAL:
        return TS_NATIONAL_RECORD
    if d in AGGREGATOR:
        return TS_AGGREGATOR
    if SYNDICATION_HINT.search(d):
        return TS_SYNDICATION
    return TS_UNKNOWN


def domains_of(raw: dict[str, Any]) -> list[str]:
    out = []
    for u in (raw.get("sourceurls") or []):
        try:
            h = urlparse(u).netloc.lower().replace("www.", "")
            if h:
                out.append(h)
        except ValueError:
            continue
    return out


# --- Ar: inverse to explicit conflict language ------------------------------
#
# GKG theme codes that ARE explicit conflict language. Presence of these is what
# drives Ar down, exactly as "they invaded"/"they stole" does in the paper.
EXPLICIT_CONFLICT_THEMES = {
    "KILL", "ARMEDCONFLICT", "TERROR", "VIOLENT_UNREST", "UNREST_CRACKDOWN",
    "UNREST_VIOLENCE", "ASSAULT", "MILITARY", "SECURITY_SERVICES", "KIDNAP",
    "TAX_TERROR_GROUP", "WOUND", "SUICIDE_ATTACK", "RAPE", "TORTURE",
    "HUMAN_RIGHTS_ABUSES", "CRISISLEX_T03_DEAD", "EXECUTION", "EXTREMISM",
    "EXILE", "GENOCIDE", "SIEGE", "SEPARATISTS", "REBELLION",
}
# Heritage / continuity framing: the high-Ar end of the paper's banding.
HERITAGE_THEMES = {
    "TAX_ETHNICITY", "CULTURE", "TRADITION", "RELIGION", "HISTORY",
    "IDEOLOGY", "EDUCATION", "SOC_POINTSOFINTEREST", "GENERAL_GOVERNMENT",
    "LEADER", "TAX_WORLDLANGUAGES", "UNGP_FORESTS_RIVERS_OCEANS",
}


def affective_resonance(themes: list[str], tone: dict[str, float]) -> float:
    """
    Ar on the paper's 1-10 band, inverse to explicit conflict language.

    Two signals, equally weighted: the share of a record's themes that are
    explicit-conflict codes, and its negative-word density. A record with no
    conflict codes and no negative affect lands near 10; one saturated with both
    lands near 1.
    """
    t = {x.strip().upper() for x in (themes or []) if x.strip()}
    if not t:
        conflict_share = 0.0
    else:
        hits = sum(1 for x in t
                   if x in EXPLICIT_CONFLICT_THEMES
                   or any(x.startswith(p + "_") for p in EXPLICIT_CONFLICT_THEMES))
        conflict_share = hits / len(t)

    neg = tone.get("negative")
    # GKG negative density runs roughly 0-10; clamp then normalise.
    neg_norm = min(max(neg or 0.0, 0.0), 10.0) / 10.0

    # Heritage framing lifts Ar, per the paper's top band.
    heritage = sum(1 for x in t if x in HERITAGE_THEMES) / len(t) if t else 0.0

    explicitness = 0.5 * conflict_share + 0.5 * neg_norm
    ar = 1.0 + 9.0 * (1.0 - explicitness)
    ar = min(10.0, ar + 0.5 * heritage)      # bounded heritage bonus
    return round(ar, 3)


# --- Cw: eigenvector centrality over the THEME co-occurrence graph -----------

def _theme_graph_centrality(records: list[list[str]], max_nodes: int = 600,
                            max_iter: int = 100, tol: float = 1e-9) -> dict[str, float]:
    """
    Eigenvector centrality over theme co-occurrence.

    A theme recurring alongside many other themes is acting as framing context
    for them — the nearest observable analogue to Manara's "referenced as
    justification for other claims". Themes are a controlled vocabulary, so
    unlike GKG entity strings they do not fragment one referent across several
    nodes, which was the defect that sank the previous Cw.
    """
    freq: dict[str, int] = {}
    for th in records:
        for x in th:
            freq[x] = freq.get(x, 0) + 1
    if not freq:
        return {}
    nodes = sorted(freq, key=lambda e: (-freq[e], e))[:max_nodes]
    idx = {e: i for i, e in enumerate(nodes)}
    n = len(nodes)
    if n < 2:
        return {nodes[0]: 1.0} if n else {}

    adj: list[dict[int, float]] = [dict() for _ in range(n)]
    for th in records:
        present = sorted({idx[x] for x in th if x in idx})
        for a in range(len(present)):
            for b in range(a + 1, len(present)):
                i, j = present[a], present[b]
                adj[i][j] = adj[i].get(j, 0.0) + 1.0
                adj[j][i] = adj[j].get(i, 0.0) + 1.0

    v = [1.0 / math.sqrt(n)] * n
    for _ in range(max_iter):
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
        if sum(abs(nv[i] - v[i]) for i in range(n)) < tol:
            v = nv
            break
        v = nv
    # Rescale to the paper's 1-10 band against the day's own maximum.
    raw = {e: v[idx[e]] for e in nodes}
    hi = max(raw.values()) or 1.0
    return {e: 1.0 + 9.0 * (val / hi) for e, val in raw.items()}


# --- assembly ---------------------------------------------------------------

def compute(case_id: int, platform: str = "gdelt_gkg") -> dict[str, dict[str, Any]]:
    """
    Daily TSI and components.

    TSI is computed per record — a record is one narrative instance — and then
    averaged over the day, so the multiplicative structure stays at the unit of
    analysis rather than being applied to three daily means.
    """
    with store.db() as conn:
        rows = conn.execute(
            "SELECT event_date, raw_json FROM records WHERE case_id=?"
            " AND source_platform=? AND event_date IS NOT NULL",
            (case_id, platform)).fetchall()

    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        raw = json.loads(r["raw_json"])
        by_day.setdefault(r["event_date"], []).append(raw)

    out: dict[str, dict[str, Any]] = {}
    for day in sorted(by_day):
        recs = by_day[day]
        theme_lists = [[x.strip().upper() for x in (rec.get("themes") or []) if x.strip()]
                       for rec in recs]
        cent = _theme_graph_centrality(theme_lists)

        tsis, cws, tss, ars = [], [], [], []
        for rec, themes in zip(recs, theme_lists):
            cw = mean([cent[t] for t in themes if t in cent]) if any(t in cent for t in themes) else 1.0
            doms = domains_of(rec)
            ts = mean([source_trust(d) for d in doms]) if doms else TS_UNKNOWN
            ar = affective_resonance(themes, rec.get("tone") or {})
            cws.append(cw); tss.append(ts); ars.append(ar)
            tsis.append(cw * ts * ar)

        out[day] = {
            "tsi": round(mean(tsis), 3),
            "cw": round(mean(cws), 3),
            "ts": round(mean(tss), 3),
            "ar": round(mean(ars), 3),
            "n": len(recs),
        }
    return out


def series(case_id: int, metric: str = "tsi",
           platform: str = "gdelt_gkg") -> dict[str, float]:
    return {d: v[metric] for d, v in compute(case_id, platform).items()}
