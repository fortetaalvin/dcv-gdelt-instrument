"""
Phase 2: Wayback recoverability for the dead URLs found in phase 1.

Phase 1 ran this check with twelve concurrent workers and archive.org returned
HTTP 429 to all of them, which scored every dead URL as unrecoverable. That was
a measurement of our own request rate, not of the archive. This pass is serial,
rate-limited and backs off on 429, and overwrites the phase-1 values.
"""
from __future__ import annotations

import json, sys, time
import requests

sys.path.insert(0, "/var/www/html/dcv")

PATH = "/var/www/html/dcv/data/linkrot.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Safari/537.36")
MIN_INTERVAL = 1.6          # seconds between requests
MAX_RETRY = 4

_last = [0.0]


def _throttle():
    dt = time.time() - _last[0]
    if dt < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - dt)
    _last[0] = time.time()


def wayback(url: str) -> bool | None:
    """True/False, or None if archive.org never gave us a usable answer."""
    for attempt in range(MAX_RETRY):
        _throttle()
        try:
            r = requests.get("https://archive.org/wayback/available",
                             params={"url": url}, timeout=30,
                             headers={"User-Agent": UA})
        except Exception:                             # noqa: BLE001
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None
        try:
            snap = (r.json().get("archived_snapshots") or {}).get("closest") or {}
        except ValueError:
            return None
        return bool(snap.get("available"))
    return None


doc = json.load(open(PATH))
dead = [(slug, row) for slug, rows in doc["results"].items()
        for row in rows if not row["alive"]]
print(f"  {len(dead)} dead URLs to check, ~{len(dead)*MIN_INTERVAL/60:.0f} min", flush=True)

t0 = time.time()
for i, (slug, row) in enumerate(dead, 1):
    row["wayback"] = wayback(row["url"])
    if i % 50 == 0:
        ok = sum(1 for _, r in dead[:i] if r.get("wayback") is True)
        un = sum(1 for _, r in dead[:i] if r.get("wayback") is None)
        print(f"    {i}/{len(dead)}  recoverable {ok}  unknown {un}"
              f"  [{time.time()-t0:.0f}s]", flush=True)
    if i % 100 == 0:
        json.dump(doc, open(PATH, "w"))

json.dump(doc, open(PATH, "w"))
print(f"\n  written {PATH}  [{time.time()-t0:.0f}s]", flush=True)
print("DONE", flush=True)
