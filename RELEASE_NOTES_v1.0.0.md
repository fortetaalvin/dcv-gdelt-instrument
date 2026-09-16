# v1.0.0 — Replication materials

Accompanies the preprint *Silent Failure Modes in GDELT-Based Crisis Research:
Twenty-Three Measured Defects and a Validation Protocol*, and the companion
findings paper on narrative crisis detection across six Nigerian cases,
2014–2024.

## Contents

- **Retrieval and analysis package** (`dcv/`) — API clients for GDELT DOC 2.0,
  GKG v1 and Events 1.0; provenance store; detection; construct implementations
- **Provenance database** (`data/provenance.sqlite`, 2.19 MB) — 4,943 logged
  retrievals with endpoint, full parameters, response SHA-256 and outcome; 13
  versioned case specifications; 4,009 daily aggregates
- **Pre-registration documents** for all three rounds, each written before the
  run it governs
- **Case specification files** (`cases/`) — both versions of each case, before
  and after keyword repair
- **Re-executable boundary probes** (`probes/`) with a dated reference run
- **Validation protocol** (`protocol/validate.py`) — thirteen checks as a
  runnable checker, exit 1 on failure

## Verifying without credentials

```bash
pip install requests
python3 probes/boundary_probes.py      # re-executes every §4.2 claim
python3 protocol/validate.py --skip-network \
  --keywords "Chibok" "Boko Haram" "schoolgirls abduction" "Borno" \
  --start 2014-03-01 --end 2014-05-15
```

The second command fails on `"schoolgirls abduction"` — the term that matched
zero records in the original study and was not caught at the time.

## Headline measurements

- **Keyword vocabularies.** Three tested over identical corpora. Descriptive
  phrases match zero records (9 of 24 pre-registered terms inert). Theme codes,
  the apparent remedy, degrade discrimination 69.4% → 59.7%. Proper nouns work
  but measure prior salience.
- **Archive non-stationarity.** Mean daily Nigerian events range 2,887 (2014) to
  5,336 (2016); peak-to-trough ratio 1.848.
- **Link rot.** From 1,200 stratified URLs: S(t) = exp(−0.0788 t), R² = 0.948,
  half-life 8.8 years. A third of sources unreachable after two years.

## Not included

Raw GDELT records (3.34M rows, ~8 GB). The provenance database records the exact
request behind every figure so each can be re-executed against GDELT directly.

## Known gaps

- Wayback recoverability unmeasured — our request pacing, not the archive. See
  `data/README.md`.
- ACLED and UCDP ground truth unavailable; consequences documented in
  `CONTINUITY.md`.

Code MIT; data and documents CC BY 4.0.
