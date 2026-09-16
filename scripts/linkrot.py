"""
Link-rot measurement across six case corpora.

Replaces an n=28 eyeball that was too small to support a rate. Design:

  - stratified by case, so rot can be read against archive age (2 to 12 years)
  - random sample without replacement, distinct URLs only
  - HEAD with redirects; GET fallback where HEAD is refused (some servers
    return 405 for HEAD while serving the page normally, which would otherwise
    be scored as rot)
  - dead URLs are then checked against the Wayback CDX API, so recoverable and
    unrecoverable loss are reported separately
  - domain origin recorded, so the source-origin question withdrawn earlier at
    n=14 per group can finally be tested at power

Wilson score intervals rather than normal approximation: proportions here run
near the boundaries where the normal approximation misbehaves.
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests

sys.path.insert(0, "/var/www/html/dcv")
from dcv import store

N_PER_CASE = 200
WORKERS = 12
TIMEOUT = 20
SEED = 20260916          # fixed so the sample is reproducible
OUT = "/var/www/html/dcv/data/linkrot.json"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "*/*"}

CASES = ["chibok_2014", "plateau_2018", "endsars_2020", "kankara_2020",
         "election_2023", "endbadgov_2024"]
AGE = {"chibok_2014": 12.4, "plateau_2018": 8.2, "endsars_2020": 5.9,
       "kankara_2020": 5.8, "election_2023": 3.5, "endbadgov_2024": 2.1}

# Nigerian-registered or Nigeria-desk outlets, for the origin test.
NG_HINT = (".ng", "nigeria", "naija", "vanguardngr", "punchng", "thisdaylive",
           "premiumtimes", "dailytrust", "thenationonline", "tribuneonline",
           "dailypost", "thecable", "leadership", "blueprint", "sunnewsonline")


def is_nigerian(domain: str) -> bool:
    d = domain.lower()
    return any(h in d for h in NG_HINT)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - s) / d), min(1.0, (c + s) / d))


def sample_urls(slug: str, n: int) -> list[str]:
    did = store.data_case_id(slug)
    seen: set[str] = set()
    with store.db() as conn:
        for r in conn.execute(
                "SELECT raw_json FROM records WHERE case_id=?"
                " AND source_platform='gdelt_gkg'", (did,)):
            for u in (json.loads(r["raw_json"]).get("sourceurls") or []):
                if u.startswith("http"):
                    seen.add(u)
    pool = sorted(seen)
    rnd = random.Random(f"{SEED}:{slug}")
    return rnd.sample(pool, min(n, len(pool)))


def check(url: str) -> dict:
    """Resolve one URL. HEAD first, GET fallback on method-not-allowed."""
    out = {"url": url, "domain": urlparse(url).netloc.lower().replace("www.", "")}
    try:
        r = requests.head(url, headers=HEADERS, timeout=TIMEOUT,
                          allow_redirects=True)
        if r.status_code in (403, 405, 501):          # HEAD refused, not dead
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                             allow_redirects=True, stream=True)
            r.close()
        out["status"] = r.status_code
        out["alive"] = 200 <= r.status_code < 400
        out["outcome"] = "alive" if out["alive"] else "http_error"
    except requests.exceptions.SSLError:
        out.update(status=None, alive=False, outcome="ssl_error")
    except requests.exceptions.ConnectionError:
        out.update(status=None, alive=False, outcome="dns_or_conn")
    except requests.exceptions.Timeout:
        out.update(status=None, alive=False, outcome="timeout")
    except Exception as exc:                          # noqa: BLE001
        out.update(status=None, alive=False, outcome=f"other:{type(exc).__name__}")
    return out


def wayback(url: str) -> bool:
    try:
        r = requests.get("https://archive.org/wayback/available",
                         params={"url": url}, timeout=TIMEOUT, headers=HEADERS)
        if r.status_code != 200:
            return False
        snap = (r.json().get("archived_snapshots") or {}).get("closest") or {}
        return bool(snap.get("available"))
    except Exception:                                 # noqa: BLE001
        return False


def main() -> None:
    results: dict[str, list[dict]] = {}
    t0 = time.time()

    for slug in CASES:
        urls = sample_urls(slug, N_PER_CASE)
        print(f"  {slug}: sampling {len(urls)} URLs", flush=True)
        rows = []
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(check, u): u for u in urls}
            for f in as_completed(futs):
                rows.append(f.result())
        dead = [r for r in rows if not r["alive"]]
        print(f"    resolved; {len(dead)} dead, checking Wayback ...", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(wayback, r["url"]): r for r in dead}
            for f in as_completed(futs):
                futs[f]["wayback"] = f.result()
        for r in rows:
            r.setdefault("wayback", None)
        results[slug] = rows
        n = len(rows); d = len(dead)
        rec = sum(1 for r in dead if r.get("wayback"))
        lo, hi = wilson(d, n)
        print(f"    {slug}: rot {d}/{n} = {100*d/n:.1f}% "
              f"[{100*lo:.1f}-{100*hi:.1f}]  wayback-recoverable {rec}/{d}"
              f"   [{time.time()-t0:.0f}s]", flush=True)

    with open(OUT, "w") as fh:
        json.dump({"seed": SEED, "n_per_case": N_PER_CASE,
                   "age_years": AGE, "results": results}, fh)
    print(f"\n  written {OUT}  [{time.time()-t0:.0f}s]", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
