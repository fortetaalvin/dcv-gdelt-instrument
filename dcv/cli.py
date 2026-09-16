"""
DCV command line.

    python3 -m dcv.cli init
    python3 -m dcv.cli cases
    python3 -m dcv.cli pull   --case endsars_2020 [--mode timelinevol]
    python3 -m dcv.cli status --case endsars_2020
    python3 -m dcv.cli graph-init
    python3 -m dcv.cli graph-stats

Analysis commands (TSI, signal detection) are deliberately absent. They depend
on SAD Open Items 1, 2 and 7, which the SAD instructs us to resolve with Alvin
rather than default. Shipping them with placeholder parameters would produce
numbers that look authoritative and are not.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import cases, gdelt, graph, store


def _build_query(keywords: list[str]) -> str:
    """
    GDELT requires OR'd terms to be parenthesised — an unwrapped disjunction is
    rejected with "Queries containing OR'd terms must be surrounded by ()".
    Multi-word terms must additionally be quoted to stay phrases.
    """
    terms = [f'"{k}"' if " " in k else k for k in keywords]
    if len(terms) == 1:
        return terms[0]
    return "(" + " OR ".join(terms) + ")"


def cmd_init(_: argparse.Namespace) -> int:
    store.init()
    for slug, spec in cases.ALL.items():
        cid = store.upsert_case(spec)
        print(f"  case {slug:<16} id={cid}")
    print("  store initialised")
    return 0


def cmd_cases(_: argparse.Namespace) -> int:
    rows = store.list_cases()
    if not rows:
        print("  no cases — run `init` first")
        return 1
    for r in rows:
        lead = r["lead_time_days"] if r["lead_time_days"] is not None else "UNSET (Open Item 2)"
        print(f"  {r['slug']:<16} v{r['version']}  {r['window_start']}..{r['window_end']}")
        print(f"  {'':16}  type={r['incident_type']}  keywords={r['keywords_status']}  lead_time={lead}")
        print(f"  {'':16}  keywords={json.loads(r['keywords_json'])}")
        if r["notes"]:
            print(f"  {'':16}  note: {r['notes']}")
        print()
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    case = store.get_case(args.case)
    if case is None:
        print(f"  unknown case: {args.case}")
        return 1

    query = _build_query(json.loads(case["keywords_json"]))
    modes = [args.mode] if args.mode else ["timelinevol", "timelinetone"]
    print(f"  case  : {case['slug']} v{case['version']}")
    print(f"  window: {case['window_start']} .. {case['window_end']}")
    print(f"  query : {query}")
    if case["keywords_status"] != "approved":
        print("  NOTE  : keyword set is provisional (SAD Open Item 4) — results are")
        print("          not paper-grade until the query strategy is fixed.")
    print()

    failed = 0
    for mode in modes:
        try:
            rows, pull_id = gdelt.fetch(
                case["case_id"], query=query, mode=mode,
                start=case["window_start"], end=case["window_end"])
            n = store.insert_records(
                [{**r, "case_id": case["case_id"], "pull_id": pull_id} for r in rows])
            print(f"  {mode:<14} {n:>5} records   pull={pull_id}")
        except gdelt.GdeltWindowUnavailable as exc:
            print(f"  {mode:<14} UNAVAILABLE  {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001 — surfaced, logged, non-fatal
            print(f"  {mode:<14} FAILED       {str(exc)[:110]}")
            failed += 1
    return 1 if failed == len(modes) else 0


def cmd_status(args: argparse.Namespace) -> int:
    case = store.get_case(args.case)
    if case is None:
        print(f"  unknown case: {args.case}")
        return 1
    print(f"  {case['slug']} v{case['version']}\n")
    rows = store.case_summary(case["case_id"])
    if not rows:
        print("  no records ingested yet")
    for r in rows:
        print(f"  {r['source_platform']:<12} {r['n']:>6} records   {r['first']} .. {r['last']}")
    print()
    with store.db() as conn:
        for p in conn.execute(
            "SELECT pull_id, source_platform, outcome, record_count, started_at"
            " FROM pulls WHERE case_id=? ORDER BY pull_id DESC LIMIT 8",
            (case["case_id"],),
        ):
            print(f"  pull {p['pull_id']:<4} {p['source_platform']:<11} "
                  f"{p['outcome']:<13} n={p['record_count']:<6} {p['started_at']}")
    return 0


def cmd_truth(args: argparse.Namespace) -> int:
    """Ground-truth ingestion (UC3). Live API, or a manual export when the edge blocks us."""
    from . import groundtruth as gt
    case = store.get_case(args.case)
    if case is None:
        print(f"unknown case: {args.case}")
        return 1

    if args.file:
        n = gt.import_file(case["case_id"], args.file, platform=args.platform)
        print(f"  imported {n} {args.platform} records from {args.file}")
        return 0

    if args.platform == "acled":
        try:
            n = gt.fetch_acled(case["case_id"], args.country,
                               case["window_start"], case["window_end"])
        except gt.EdgeChallenged as exc:
            print(f"  BLOCKED: {exc}")
            print("  Download the window from acleddata.com in a browser, then:")
            print(f"    python3 -m dcv.cli truth --case {args.case} --file <export.csv>")
            return 2
    else:
        n = gt.fetch_ucdp(case["case_id"], args.country_id,
                          int(case["window_start"][:4]), int(case["window_end"][:4]))
    print(f"  ingested {n} {args.platform} records")
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    """GDELT Events 1.0 ingestion. v2 cannot reach 2014 — see dcv/events.py."""
    from . import events
    case = store.get_case(args.case)
    if case is None:
        print(f"unknown case: {args.case}")
        return 1
    totals = events.ingest_window(case["case_id"],
                                  args.start or case["window_start"],
                                  args.end or case["window_end"])
    print(f"  {totals}")
    return 0


def cmd_views(args: argparse.Namespace) -> int:
    """ViEWS benchmark. Reports coverage first — it does not cover either case."""
    from . import views
    runs = views.list_runs()
    run = args.run or views.earliest_run(runs)
    cov = views.coverage(run, iso=args.iso)
    print(f"  runs available   : {len(runs)}  (earliest {views.earliest_run(runs)})")
    print(f"  run              : {run}")
    print(f"  forecast starts  : {cov['forecast_start']}")
    print(f"  rows span        : {cov['months_first']} .. {cov['months_last']}"
          f"  (n={cov['row_count']})")
    if args.case:
        case = store.get_case(args.case)
        if case is None:
            print(f"unknown case: {args.case}")
            return 1
        trig = min(json.loads(case["trigger_dates"]))
        y, m = int(trig[:4]), int(trig[5:7])
        inside = (y, m) in cov["months_present"]
        print(f"  trigger {trig} covered: {inside}")
        if not inside:
            print("  -> ViEWS has no forecast for this case's trigger month.")
            return 2
        print(f"  stored {views.fetch(case['case_id'], run, iso=args.iso)} rows")
    return 0


def cmd_analyse(args: argparse.Namespace) -> int:
    from . import analysis
    res = analysis.analyse(args.case)
    print(analysis.report(res))
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=2)
        print(f"\n  written: {args.json}")
    return 0


def cmd_params(_: argparse.Namespace) -> int:
    from . import parameters
    print(parameters.summary())
    return 0


def cmd_graph_init(_: argparse.Namespace) -> int:
    for name in graph.init():
        print(f"  constraint/index ensured: {name}")
    return 0


def cmd_graph_stats(args: argparse.Namespace) -> int:
    for k, v in graph.stats(args.case).items():
        print(f"  {k:<16} {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dcv", description="DEJM Crisis Detection Pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create store and seed case specs").set_defaults(fn=cmd_init)
    sub.add_parser("cases", help="list case specifications").set_defaults(fn=cmd_cases)

    p = sub.add_parser("pull", help="pull GDELT data for a case")
    p.add_argument("--case", required=True)
    p.add_argument("--mode", choices=["timelinevol", "timelinetone", "artlist"])
    p.set_defaults(fn=cmd_pull)

    p = sub.add_parser("status", help="ingestion status for a case")
    p.add_argument("--case", required=True)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("truth", help="ingest ACLED / UCDP ground-truth events")
    p.add_argument("--case", required=True)
    p.add_argument("--platform", default="acled", choices=["acled", "ucdp_ged"])
    p.add_argument("--file", help="load a manual export instead of calling the API")
    p.add_argument("--country", default="Nigeria", help="ACLED country name")
    p.add_argument("--country-id", type=int, default=475, help="UCDP country id (Nigeria=475)")
    p.set_defaults(fn=cmd_truth)

    p = sub.add_parser("events", help="ingest GDELT Events (CAMEO/Goldstein)")
    p.add_argument("--case", required=True)
    p.add_argument("--start"); p.add_argument("--end")
    p.set_defaults(fn=cmd_events)

    p = sub.add_parser("views", help="ViEWS forecast coverage / ingest")
    p.add_argument("--case", default=None)
    p.add_argument("--run", default=None)
    p.add_argument("--iso", default="NGA")
    p.set_defaults(fn=cmd_views)

    p = sub.add_parser("analyse", help="UC6 signal detection and trend contrast")
    p.add_argument("--case", required=True)
    p.add_argument("--json", default=None, help="write full result to this path")
    p.set_defaults(fn=cmd_analyse)

    sub.add_parser("params", help="show fixed analysis parameters").set_defaults(fn=cmd_params)

    sub.add_parser("graph-init", help="apply graph constraints").set_defaults(fn=cmd_graph_init)

    p = sub.add_parser("graph-stats", help="node/edge counts")
    p.add_argument("--case", default=None)
    p.set_defaults(fn=cmd_graph_stats)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
