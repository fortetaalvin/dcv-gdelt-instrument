# Pre-registration v1 — round 1 analysis parameters

**Stamped 2026-09-15, before any detection result existed.**

Machine-readable source: `dcv/parameters.py`, `PARAMETERS_VERSION = "1.0"`,
`FIXED_ON = "2026-09-15"`. This document is the human-readable record of the
same values. Where the two disagree, the module is authoritative.

The purpose of fixing these in advance is narrow and specific: a lead-time
threshold chosen after seeing the series is not a threshold, it is a
description. Holding the values in one version-stamped module is what makes the
claim checkable rather than asserted.

## Lead-time threshold (SAD Open Item 2)

| Case | Primary target | Rationale |
|---|---|---|
| `endsars_2020` | **14 days** | Structural early-warning systems (VIEWS, ACLED CAST) forecast at monthly horizons, but media-narrative signals move faster; the #EndSARS build-up ran roughly three weeks. Two weeks is long enough for a response to be possible and short enough that attention is plausibly about the coming event rather than the general climate. |
| `chibok_2014` | **None** | Assigned to Model B (crisis precedes narrative), where lead time does not apply. Recorded as `None` rather than omitted, so the absence is explicit. |

Sensitivity ladder: **7 / 14 / 28 / 56 days**, taken from the design document's
own specification of 1, 2, 4 and 8 weeks, so that the primary threshold and the
sensitivity analysis share one scale rather than being invented separately.

## Directional model assignment

Committed before analysis:

- **Model A — narrative precedes crisis.** Assigned to `endsars_2020`.
- **Model B — crisis precedes narrative.** Assigned to `chibok_2014`.

Assigning direction in advance matters because, run the other way round, any
result would have been compatible with some post-hoc story.

## Incident-type taxonomy (Open Item 5)

Five types confirmed unchanged from the design document — insurgency, protest
movement, banditry/kidnapping, communal violence, economic-trigger crisis — with
ACLED and UCDP event-code mappings added. The addition is necessary because the
taxonomy is phenomenon-based while the ground-truth datasets classify by event
form; without a mapping, extracted claims cannot be joined to coded events.

Recorded at the same time: **UCDP codes no protest category at all.** For
protest cases ACLED is therefore the sole ground truth, and any measure defined
over ACLED/UCDP divergence is undefined for that entire class of event.

## Extraction validation (Open Item 9)

- Sample size **100 per case** (n = 96 gives ±10 percentage points at 95%
  confidence for an unknown proportion; rounded up, and also the conventional
  floor in content-analysis reliability work)
- Sampling: random without replacement, stratified by pre/post trigger
- Precision ≥ 0.80, recall ≥ 0.70, Krippendorff's α ≥ 0.80

Recall is set below precision deliberately. Extraction runs mostly on GKG
metadata rather than article text, so a claim absent from the metadata cannot be
recovered and counts against recall through no fault of the model. Precision is
the binding constraint, because a false claim propagates downstream.

## Detection rule

Fixed before use: baseline from the first 28 days of the window; fire on the
first day exceeding `baseline mean + k·SD` for `p` consecutive days; sweep
k ∈ {1.5, 2.0, 2.5, 3.0} and p ∈ {1, 2, 3} and report the whole surface rather
than a chosen cell.

Lead time is signed: **positive is early warning, zero or negative is
after-the-fact detection**, reported as such rather than rounded into a success.

## Known limitation, recorded at the time

The keyword sets were selected by a sensitivity sweep over the same corpora the
analysis uses. They were frozen before the analysis below, but they were not
chosen blind to the data. A fully clean design would select keywords on a
held-out case.

## What this round did not know

Round 1 was run against a project specification that mis-stated the index it was
meant to validate — see `PREREGISTRATION_v3.md` and §7 of the methods paper.
That error is not visible in this document because it was not known when this
document was written. It is noted here so the record is not read as cleaner than
it was.
