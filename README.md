# Silent Failure Modes in GDELT-Based Crisis Research

Replication materials for:

> Forteta, A. O. (2026). *Silent Failure Modes in GDELT-Based Crisis Research:
> Twenty-Three Measured Defects and a Validation Protocol.* Preprint.

and for the companion findings paper on narrative crisis detection across six
Nigerian cases, 2014–2024.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.PENDING.svg)](https://doi.org/10.5281/zenodo.PENDING)

**Repository:** `github.com/fortetaalvin/dcv-gdelt-instrument` ·
**Working locations and open items:** [`CONTINUITY.md`](CONTINUITY.md)

---

## What this repository contains

| Path | Contents |
|---|---|
| `dcv/` | The retrieval and analysis package — every API client, the provenance store, detection, and the construct implementations |
| `data/provenance.sqlite` | **4,943 logged retrievals**: endpoint, full parameters, response SHA-256, outcome. Plus case specifications and 4,009 daily aggregates |
| `preregistration/` | Pre-registration documents for all three rounds, each written before the run it governs |
| `cases/` | Case specification files as JSON, both versions of each (v1 original, v2 after keyword repair) |
| `probes/` | Re-executable boundary probes for methods paper §4.2, plus a recorded run |
| `protocol/` | The thirteen-step validation protocol as a runnable checker, not prose |
| `scripts/` | Ingestion and analysis drivers for each round |
| `data/*.json` | Analysis outputs: round 2, round 3, round 4, link rot, dashboard |

## What this repository does **not** contain

**Raw GDELT records.** The study retrieved 3.34 million GKG and Events records
plus 16.4 million aggregated events. Redistributing them would be a large copy
of someone else's publicly available data, and would obscure rather than aid
verification.

Instead, `data/provenance.sqlite` records the **exact request** behind every
figure — endpoint, parameters, response hash, outcome, timestamps — so any
number can be traced to the retrieval that produced it and that retrieval can be
re-executed directly against GDELT. Failed retrievals are recorded with the same
fidelity as successes (13 rejected, 7 error, 4 rate-limited), because an empty
series and an unavailable series are different facts.

---

## Quick verification (no credentials, ~4 minutes)

Everything below runs against public endpoints.

```bash
pip install requests

# 1. Re-execute every archive-boundary claim in methods paper §4.2
python3 probes/boundary_probes.py

# 2. Run the validation protocol against a deliberately broken keyword set
python3 protocol/validate.py --skip-network \
  --keywords "Chibok" "Boko Haram" "schoolgirls abduction" "Borno" \
  --start 2014-03-01 --end 2014-05-15
# -> FAILs on "schoolgirls abduction", which matched zero records in the study

# 3. Inspect the provenance database
sqlite3 data/provenance.sqlite \
  "SELECT source_platform, outcome, COUNT(*) FROM pulls GROUP BY 1,2;"
```

`probes/last_run.txt` holds a recorded execution with its date, so a reviewer can
compare today's result against ours. A `FAIL` there is not necessarily an error
in the paper: these are dated measurements of a live service, and a mismatch
means GDELT's behaviour has changed — which is itself worth knowing.

---

## Reproducing the analysis

Retrieval is the expensive step: roughly 5,000 requests and several hours,
mostly rate-limited waiting. The analysis steps run in minutes from the stored
outputs.

```bash
# Recreate the store and seed case specifications
python3 -m dcv.cli init
python3 -m dcv.cli cases

# Retrieval (slow — GDELT requires 15s spacing on the DOC API; see §4.3.1)
python3 scripts/ingest_events.py          # six case windows, Events 1.0
python3 scripts/ingest_round2.py          # round-2 cases, GKG + Events
python3 scripts/ingest_continuous.py      # 4,009 continuous days

# Analysis
python3 scripts/run_round2.py             # detection across six cases
python3 scripts/round4.py                 # continuous rolling detection
python3 scripts/linkrot.py                # 1,200-URL link rot sample
python3 scripts/compute_all.py            # all constructs -> data/dashboard.json
```

Analysis outputs are committed in `data/`, so results can be inspected without
re-retrieving anything.

### A note on link rot

`scripts/linkrot.py` resolves URLs concurrently, which is fine. Its companion
`scripts/linkrot_wayback.py` queries the Internet Archive, which is **not** fine
concurrently — our first attempt was rate-limited and scored every URL as
unrecoverable, a measurement of our own request rate rather than of the archive.
The recoverability figure is therefore absent from the paper. Pace archive.org
from the first request.

---

## Findings at a glance

The defects are documented in the methods paper. The two with the widest
implications:

**Keyword vocabularies.** Three tested over identical corpora. Descriptive
phrases match zero records — nine of twenty-four terms in our own pre-registered
sets were inert. Native theme codes, the obvious remedy, made discrimination
*worse* (69.4% → 59.7%) because they index national topic volume. Proper nouns
work but measure prior salience.

**Archive non-stationarity.** Mean daily Nigerian events range from 2,887 (2014)
to 5,336 (2016), a peak-to-trough ratio of 1.848. Any study comparing raw
volumes across periods is confounded by the archive's own growth.

**Link rot.** From a 1,200-URL stratified sample: exponential decay,
S(t) = exp(−0.0788 t), R² = 0.948, half-life **8.8 years**. A third of sources
are unreachable two years after publication.

---

## Requirements

Python 3.10+ and `requests`. The graph module additionally uses `neo4j`, but no
finding in either paper depends on it.

Optional credentials, none required for anything above: `ACLED_EMAIL` /
`ACLED_PASSWORD` (OAuth2 password grant — note ACLED's edge challenges
datacenter IPs, see §4.3.2) and `UCDP_TOKEN`. Place them in `docker/.env`, which
is gitignored.

---

## Licence

Code (`dcv/`, `scripts/`, `probes/`, `protocol/`): **MIT**.
Data and documents (`data/`, `cases/`, `preregistration/`): **CC BY 4.0**.

GDELT is a project of The GDELT Project and is separately licensed; this
repository redistributes none of it.

## Citation

See `CITATION.cff`, or cite the Zenodo DOI above.
