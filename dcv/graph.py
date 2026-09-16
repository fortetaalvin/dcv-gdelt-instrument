"""
Neo4j knowledge graph (SAD Section 7).

Runs against the dedicated dcv-neo4j instance, not the OIRE one. Neo4j Community
supports a single user database, so separation is by container rather than by
database name — see docker/compose.yaml.

Ground-truth Event nodes (ACLED/UCDP) and LLM-extracted Claim nodes are kept
structurally distinct. UC-N2 depends on being able to ask "does this claim match
a coded event?", which is only answerable if the two never merge.
"""
from __future__ import annotations

from typing import Any, Iterable

from neo4j import GraphDatabase

from .config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

# Section 7 node types: Actor, Location, Event, Source, Claim
CONSTRAINTS = [
    "CREATE CONSTRAINT actor_name IF NOT EXISTS FOR (a:Actor) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT loc_name  IF NOT EXISTS FOR (l:Location) REQUIRE l.name IS UNIQUE",
    "CREATE CONSTRAINT src_url   IF NOT EXISTS FOR (s:Source) REQUIRE s.url IS UNIQUE",
    "CREATE CONSTRAINT event_key IF NOT EXISTS FOR (e:Event) REQUIRE e.event_key IS UNIQUE",
    "CREATE CONSTRAINT claim_key IF NOT EXISTS FOR (c:Claim) REQUIRE c.claim_key IS UNIQUE",
    "CREATE INDEX event_date IF NOT EXISTS FOR (e:Event) ON (e.date)",
    "CREATE INDEX claim_case IF NOT EXISTS FOR (c:Claim) ON (c.case_slug)",
]


def driver():
    if not NEO4J_PASSWORD:
        raise RuntimeError("DCV_NEO4J_PASSWORD not set — see docker/.env")
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def init() -> list[str]:
    applied = []
    with driver() as d, d.session() as s:
        for stmt in CONSTRAINTS:
            s.run(stmt)
            applied.append(stmt.split()[2])
    return applied


def load_ground_truth_events(case_slug: str, events: Iterable[dict[str, Any]]) -> int:
    """
    UC4 — ACLED/UCDP records become Event nodes.

    `event_key` is source_dataset + native id, so the same incident coded by both
    ACLED and UCDP produces TWO nodes, not one. That is deliberate: dataset
    divergence is an input to Ts (UC5), so reconciling here would destroy the
    signal the SAD asks us to measure.
    """
    rows = list(events)
    if not rows:
        return 0
    cypher = """
    UNWIND $rows AS r
    MERGE (e:Event {event_key: r.event_key})
      SET e.date = r.date, e.type = r.type, e.source_dataset = r.source_dataset,
          e.fatalities = r.fatalities, e.description = r.description,
          e.case_slug = $case_slug
    WITH e, r WHERE r.location IS NOT NULL
    MERGE (l:Location {name: r.location})
    MERGE (e)-[:LOCATED_AT]->(l)
    WITH e, r WHERE r.actor IS NOT NULL
    MERGE (a:Actor {name: r.actor})
    MERGE (a)-[:PARTICIPATED_IN]->(e)
    """
    with driver() as d, d.session() as s:
        s.run(cypher, rows=rows, case_slug=case_slug)
    return len(rows)


def load_sources(case_slug: str, sources: Iterable[dict[str, Any]]) -> int:
    """GDELT articles become Source nodes; MENTIONS edges feed Cw centrality."""
    rows = [r for r in sources if r.get("url")]
    if not rows:
        return 0
    cypher = """
    UNWIND $rows AS r
    MERGE (s:Source {url: r.url})
      SET s.outlet = r.outlet, s.language = r.language,
          s.publication_date = r.publication_date, s.case_slug = $case_slug
    WITH s, r
    UNWIND coalesce(r.mentions, []) AS m
    MERGE (a:Actor {name: m})
    MERGE (s)-[:MENTIONS]->(a)
    """
    with driver() as d, d.session() as s:
        s.run(cypher, rows=rows, case_slug=case_slug)
    return len(rows)


def stats(case_slug: str | None = None) -> dict[str, int]:
    where = "WHERE n.case_slug = $slug" if case_slug else ""
    with driver() as d, d.session() as s:
        out: dict[str, int] = {}
        for label in ("Actor", "Location", "Event", "Source", "Claim"):
            q = f"MATCH (n:{label}) {where} RETURN count(n) AS n"
            out[label] = s.run(q, slug=case_slug).single()["n"]
        rel = s.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
        out["relationships"] = rel
        return out


def reset(case_slug: str) -> int:
    """Remove one case's subgraph. Scoped by case_slug so it cannot take others."""
    with driver() as d, d.session() as s:
        rec = s.run("MATCH (n) WHERE n.case_slug = $slug DETACH DELETE n RETURN count(n) AS n",
                    slug=case_slug).single()
        return rec["n"] if rec else 0
