# Working locations and state

Orientation for anyone — including a future AI session — resuming work on this
project. Everything published lives in this repository; this file records where
the working copies are and what is outstanding.

## Canonical locations

| What | Where |
|---|---|
| **Repository (authoritative)** | `github.com/fortetaalvin/dcv-gdelt-instrument` |
| Zenodo archive | concept DOI `10.5281/zenodo.22801923` (all versions) · v1.0.0 `10.5281/zenodo.22801924` |
| Working copy of this repo | `/var/www/html/dcv-repo` (Contabo VPS) |
| Live project directory | `/var/www/html/dcv` — full store including raw records |
| Live dashboard | `dcv.forteta.ng` (Apache vhost, DocumentRoot `/var/www/html/dcv/web`) |

## Documents

| Document | Working file | Published |
|---|---|---|
| Methods preprint (*Silent Failure Modes*) | `/var/www/html/dcv/web/methods.html` | Artifact `bf0e7dc6-0241-42d1-bd9e-f6e8d1e0c063` |
| Findings paper (*Mobilisation and Silence*) | `/var/www/html/dcv/web/paper.html` | Artifact `e32029d9-0d44-4b67-bc88-e635efe12a58` |
| Instrument panel | `/var/www/html/dcv/web/index.html` | Artifact `9f9d0932-b306-4c12-a6d6-4d10725ea7e2` |

Artifacts are republished to the **same URL** by writing the working file and
re-publishing that path. Creating a new artifact instead of updating the
existing one breaks every link already circulated.

The dashboard is generated, not hand-edited: `scripts/compute_all.py` writes
`data/dashboard.json`, then `scripts/build_dashboard.py` renders
`web/_dashboard_template.html` into `web/index.html`.

## Source documents (not in this repository)

Both are the author's own work and are not redistributed here:

- `FINAL Thesis -- Iteration 51.pdf` — Forteta (2026), *Digital Governance in
  Disruptive Contexts*, 379pp. Defines CVD, TIF's four modes, RVSM, System D's
  algedonic filter and Cynefin routing.
- `_Final-Manara-Paper.pdf` — Usman, Forteta, Bello, Bakari & Ingio (2026).
  Defines **TSI = Cw × Ts × Ar**, the Tacit Score Index.

Both sit in `/var/www/html/dcv/` on the working server. Anyone extending the
construct implementations in `dcv/manara.py` or `dcv/thesis_metrics.py` should
read the relevant sections rather than work from a summary — an earlier round of
this project was built from a project specification that mis-stated TSI's name,
formula and all three component definitions, and three rounds of work were
affected before the source paper was consulted.

## State

**Settled.** Four analysis rounds complete. The protest-event channel separates
mobilisational from clandestine crises at 3/3 and 0/3 under a prospective
rolling baseline, 1.65 alarms/year over 11 years, p = 0.0011. Keyword
vocabularies tested three ways. Link rot measured at n = 1,200. Twenty-four
instrument defects documented.

**Open.**

1. **Ground truth.** The binding constraint on everything. Detailed below.
2. **Wayback recoverability.** Unmeasured — see `data/README.md`. Needs a run
   paced from the first request.
3. **Round 5.** Cases selected by rule rather than by the author, in a country
   the author has not worked on, to test whether the protest-channel result
   survives. Expected to weaken.
4. **TSI in its own domain.** The index was built for closed trusted
   micro-publics where quietness signals danger, not open media. Testing it
   against the Mubi fieldwork is a different project.
5. **Future releases.** Each new release mints a new version DOI under the same
   concept DOI. Cite the concept DOI; pin the version DOI only for an exact
   snapshot.
6. **Methods paper submission.** Preprint v2.2 is published and archived. Target
   venue *Big Data & Society*; APC $1,500 with a waiver requestable on
   acceptance for authors without OA funding. Check whether Nigeria has moved
   into Research4Life Group A (automatic full waiver) — plausible after the
   2023-24 devaluation, since Group A admits total GNI under US$200bn where HDI
   is at or below 0.60.
7. **Findings paper.** *Mobilisation and Silence* is at v0.4 and not submitted.
   It depends on round 5 and on ground truth.

## ACLED — what is needed, and what it unlocks

The single blocker on round 5, on precision, and on the CVD denominator.

### Access — three routes, easiest first

1. **Set a password on the myACLED account.** The API uses an OAuth2 password
   grant against `https://acleddata.com/oauth/token`. An account created through
   Google sign-in has no password, and the grant then fails on credentials that
   look correct. This may be the entire problem.
2. **Request an IP allowlist for 169.58.84.78.** Every path on `acleddata.com`
   returns HTTP 403 with `cf-mitigated: challenge` to this host, including the
   public homepage — an edge decision about the datacenter IP, not the account.
   No credential or User-Agent clears it.
3. **Manual export.** Download in a browser, then
   `python3 -m dcv.cli truth --case <slug> --file <export.csv>`. Already built;
   records the file SHA-256 and marks the pull `manual_export`.

### The request

Nigeria, **2014-01-01 to 2024-12-31**, **all event types** — filtering to
protest would rebuild the selection bias the exercise exists to escape. Fields:
`event_id_cnty`, `event_date`, `event_type`, `sub_event_type`, `actor1`,
`actor2`, `admin1`, `admin2`, `location`, `fatalities`, `notes`, `source`,
`source_scale`. API caps at 5,000 rows per call; paginate or take a bulk export.

### What it unlocks

- **A denominator.** `|need| = 6` only because six crises were enumerated, which
  is why J = 0.1429 is an upper bound. ACLED makes need measurable.
- **Precision with a ceiling.** 15 of 18 alarms are unattributed; precision has
  a floor of 0.167 and no defensible top. This is the weakest number in the
  findings paper.
- **Round 5 at all.** Rule-selected cases need a criterion to select on. GDELT
  Events codes no fatalities, so there is none without ACLED.
- **UC-N2** claim verification against coded events.

### What it does NOT unlock

**Ts.** Earlier rounds reported TSI as blocked because Ts required ACLED/UCDP
divergence. That came from the project specification and is wrong — the Manara
paper defines Ts as a source-trust ranking. ACLED/UCDP divergence may still be a
useful reliability measure, but it is not Ts and must not be labelled as such.

### Licensing

ACLED's terms restrict redistribution and **this repository is public**. ACLED
data belongs in the local store and the analysis, never in the repo. A
`.gitignore` rule is in place so this does not depend on remembering.

## Conventions that are load-bearing

- **Word-boundary matching everywhere.** Substring matching has caused three
  separate defects in this project (`SARS` inside `ENDSARS`, `boko` inside
  `bokor`, `Jos` inside `Joseph`).
- **Empty is an error, not a result.** A keyword matching nothing, a
  boundary-rejected date and an orphaned case version all return empty series
  silently. `dcv/store.py:data_case_id()` raises rather than returning empty;
  `protocol/validate.py` fails the run on a dead keyword.
- **Failures are rows.** Every retrieval writes a `pulls` row including
  `rejected`, `rate_limited` and `error`. An empty series and an unavailable
  series are different facts.
- **Case specs are versioned, data is not re-ingested.** A keyword revision
  creates a new `cases` version owning zero records; analysis resolves records
  via `data_case_id()`.
- **Differences, not ratios, on signed series.** Goldstein and Ar both invert
  under a ratio of two negatives.
- **Pre-register before running.** Three rounds are recorded in
  `preregistration/`. Round 2's hypothesis was refuted by its own stated
  falsification rule, which is the point of writing it down first.
