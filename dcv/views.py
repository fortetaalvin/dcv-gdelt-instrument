"""
ViEWS forecast ingestion (comparative benchmark layer).

ViEWS (Violence Early-Warning System, Uppsala) publishes subnational and
country-month violence forecasts with known accuracy scores. It is the obvious
benchmark for a claim that narrative signal adds predictive value — which is
exactly why its coverage had to be checked before the claim was made rather
than after.

**Measured 2026-09-15: ViEWS covers neither case.**

    GET /                        -> 90 runs, earliest `d_2021_02_01`
    GET /d_2021_02_01/cm/sb?iso=NGA
        start_date  495          (= 2021-04)
        rows        2016-01 .. 2024-02
        2014 rows   0
        2020-10     absent

Two separate facts, both load-bearing:

1. **No run predates 2021-02.** The public API's earliest forecast run was
   published in February 2021 — ten months after #EndSARS and nearly seven
   years after Chibok. Whatever ViEWS says about those periods today, no such
   forecast was on anyone's desk at the time.

2. **Even retrospectively, the window misses.** The earliest run's rows begin
   2016-01, so Chibok is outside the data entirely, and 2020-10 is absent from
   that run's country-month series for Nigeria.

This is a negative result, and it is reported as one rather than quietly
dropped. It also sharpens the paper's argument: for both cases the *narrative*
record existed contemporaneously and the *structural forecast* did not. An
appeal to "they should have used the forecasting systems" has no referent in
2014 or 2020 Nigeria.

The client is still built, for three reasons: it documents the negative result
reproducibly, it is the benchmark for any case from 2021 onward, and it is
required the moment this scales to other countries where ViEWS does cover the
period of interest.
"""
from __future__ import annotations

import json
from typing import Any

import requests

from . import store

VIEWS_API = "https://api.viewsforecasting.org"

# ViEWS month_id is months since 1980-01, which is month_id 1.
MONTH_ID_EPOCH_YEAR = 1980


class ViewsError(RuntimeError):
    pass


def month_id(year: int, month: int) -> int:
    return (year - MONTH_ID_EPOCH_YEAR) * 12 + month


def from_month_id(mid: int) -> tuple[int, int]:
    y, m = divmod(mid - 1, 12)
    return MONTH_ID_EPOCH_YEAR + y, m + 1


def list_runs() -> list[str]:
    resp = requests.get(f"{VIEWS_API}/", timeout=60)
    if resp.status_code != 200:
        raise ViewsError(f"ViEWS run list HTTP {resp.status_code}")
    return resp.json().get("runs", [])


def earliest_run(runs: list[str] | None = None) -> str:
    """
    Lexically smallest run name. Run names embed the publication date
    (`<model>_<YYYY>_<MM>_<DD>`), so this is also the chronologically earliest
    for any one model family.
    """
    return sorted(runs or list_runs())[0]


def coverage(run: str, iso: str = "NGA", level: str = "cm",
             outcome: str = "sb") -> dict[str, Any]:
    """
    What months does this run actually carry for a country?

    Used to establish, reproducibly, whether a case falls inside ViEWS at all.
    Returns the forecast window, the observed row span, and the row count —
    enough for the non-coverage claim above to be re-checked by a reader.
    """
    url = f"{VIEWS_API}/{run}/{level}/{outcome}"
    resp = requests.get(url, params={"iso": iso, "pagesize": 1000}, timeout=90)
    if resp.status_code != 200:
        raise ViewsError(f"ViEWS {run} HTTP {resp.status_code}: {resp.text[:200]}")
    doc = resp.json()
    rows = doc.get("data", [])
    months = sorted({(r.get("year"), r.get("month")) for r in rows})
    return {
        "run": run, "iso": iso, "level": level, "outcome": outcome,
        "forecast_start_month_id": doc.get("start_date"),
        "forecast_start": from_month_id(doc["start_date"]) if doc.get("start_date") else None,
        "forecast_end_month_id": doc.get("end_date"),
        "row_count": doc.get("row_count"),
        "months_first": months[0] if months else None,
        "months_last": months[-1] if months else None,
        "months_present": months,
        "models": doc.get("models"),
    }


def covers(run: str, year: int, month: int, iso: str = "NGA") -> bool:
    return (year, month) in coverage(run, iso)["months_present"]


def fetch(case_id: int, run: str, iso: str = "NGA", level: str = "cm",
          outcome: str = "sb") -> int:
    """
    Store one ViEWS run's country-month forecasts as SAD §8 records.

    `event_date` is set to the first of the forecast month. A ViEWS row is a
    *prediction about* a month, not an observation in it, so `event_type` names
    it `views_forecast` and the run name — which encodes when the forecast was
    published — is kept in `raw_json`. Conflating a forecast with an observation
    is precisely the error the benchmark exists to avoid.
    """
    url = f"{VIEWS_API}/{run}/{level}/{outcome}"
    params = {"iso": iso, "pagesize": 1000}
    pull_id = store.open_pull(case_id, "views", url, {**params, "run": run})

    try:
        resp = requests.get(url, params=params, timeout=120)
    except Exception as exc:                          # noqa: BLE001
        store.close_pull(pull_id, outcome="error", error=str(exc)[:400])
        raise

    if resp.status_code != 200:
        store.close_pull(pull_id, outcome="rejected", status=resp.status_code,
                         error=resp.text[:400])
        raise ViewsError(f"ViEWS HTTP {resp.status_code}")

    doc = resp.json()
    data = doc.get("data", [])
    retrieved = store.now()
    method = f"GET {url} {json.dumps(params, sort_keys=True)} (run published {run})"

    rows = []
    for r in data:
        y, m = r.get("year"), r.get("month")
        if not y or not m:
            continue
        # The headline probability varies by run generation; take the main
        # model where present and fall back to the ensemble.
        score = r.get("sc_cm_sb_main")
        if score is None:
            score = r.get("sc_cm_sb_all_global")
        rows.append({
            "case_id": case_id, "pull_id": pull_id,
            "source_platform": "views",
            "source_record_id": f"{run}:{r.get('country_id')}:{r.get('month_id')}",
            "event_date": f"{y:04d}-{m:02d}-01",
            "event_type": "views_forecast",
            "location": r.get("name"),
            "content_summary": None,
            "tone_score": score,
            "fatalities": None,
            "language": None,
            "retrieval_method": method,
            "retrieved_at": retrieved,
            "raw_json": json.dumps({**r, "run": run, "level": level,
                                    "outcome": outcome}, sort_keys=True),
        })

    store.insert_records(rows)
    store.close_pull(pull_id, outcome="success" if rows else "empty",
                     status=200, count=len(rows))
    return len(rows)
