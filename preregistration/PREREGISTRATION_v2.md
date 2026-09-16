# Pre-registration — falsification round

**Stamped 2026-09-16, before any data for these four cases was retrieved.**

Round 1 (Chibok, #EndSARS) produced a hypothesis from two cases. This round
exists to try to break it. The predictions below are recorded first so that a
wrong prediction is visible as a wrong prediction rather than reinterpreted
afterwards.

## Hypothesis under test

> **H1 (mobilisation).** The detectability of a crisis in narrative data is a
> function of whether the crisis requires public mobilisation to occur.
> Mobilisational crises (protest movements, organised civil action) carry a
> pre-trigger narrative signal with usable lead time. Clandestine crises
> (abduction, ambush, massacre) do not.

## Predictions

| Case | Type | Model predicted | Lead-time target |
|---|---|---|---|
| `kankara_2020` | banditry/kidnapping | **B** — no pre-trigger signal | none (N/A under B) |
| `plateau_2018` | communal violence | **B** — no pre-trigger signal | none (N/A under B) |
| `election_2023` | protest movement | **A** — pre-trigger signal | **≥14 days** |
| `endbadgov_2024` | economic-trigger crisis | **A** — pre-trigger signal | **≥14 days** |

## What would falsify H1

- Any clandestine case firing with a **positive lead ≥7 days** on the
  case-specific narrative channel, stable across the threshold sweep.
- Either mobilisational case failing to fire before its trigger, or firing with
  lead < 7 days.
- Lead times that do not separate the two groups at all.

A mixed result does not rescue H1. Two of four in the wrong direction means the
hypothesis does not survive in its current form and must be narrowed or dropped.

## Known confound, recorded in advance

`election_2023` is anchored on a **scheduled** public event. Narrative attention
rises before any general election regardless of whether a crisis follows, so a
positive lead here is weak evidence for H1 — it may measure calendar
anticipation rather than crisis anticipation. It is retained deliberately as an
adversarial case: if the instrument cannot distinguish a scheduled political
event from an emerging crisis, that is a limitation worth surfacing, and this
case is where it will show.

`endbadgov_2024` is the cleaner mobilisational test: the protest date was
announced in advance by organisers, but the crisis itself was not scheduled by
the state.

### Second confound, found at seeding time (still before retrieval)

`kankara_2020` has window 2020-10-23 → 2021-01-06, so its 28-day baseline
(2020-10-23 → 2020-11-19) sits **inside the #EndSARS aftermath**. The
case-specific keyword channel is insulated — the term sets do not overlap — but
every structural channel is Nigeria-wide and will carry #EndSARS residue in its
baseline.

The direction of this bias matters and is stated before the result is known: an
inflated baseline makes the threshold harder to cross, which pushes Kankara
*toward* the predicted Model B outcome. **A null result for Kankara is therefore
weak evidence for H1**, because the confound predicts the same thing H1 does.
Only the keyword channel is diagnostic for this case. A Kankara *positive* would
be strong evidence against H1, since it would have to overcome the bias.

## Method held constant from round 1

- Windows: **trigger − 49 days to trigger + 26 days** (76 days), matching the
  #EndSARS window exactly.
- Sources: GDELT GKG v1 (narrative) and GDELT Events 1.0 (structural), both
  verified available for every date in all four windows before registration.
- Detection: baseline = first 28 days; fire on `mean + k·SD` sustained for
  `p` days; sweep k ∈ {1.5, 2.0, 2.5, 3.0}, p ∈ {1, 2, 3}.
- Keyword sets are fixed below and are **not** revised after seeing results.
  They follow the round-1 pattern: place name, principal actor, event
  descriptor, region.

## Keyword sets (frozen)

- `kankara_2020`: Kankara, Katsina, banditry, schoolboys abduction
- `plateau_2018`: Plateau, Barkin Ladi, Jos, herder farmer
- `election_2023`: INEC, election protest, Obidient, presidential election Nigeria
- `endbadgov_2024`: EndBadGovernance, hunger protest, Nigeria protest, fuel subsidy

## TSI

TSI = Cw × Ts × As per SAD §3. **Ts is not computable in this round**: it
requires ACLED/UCDP dataset divergence and UC-N2 claim verification against
ground truth, and both ground-truth sources remain inaccessible (ACLED edge
challenge; UCDP token). Anything reported as a complete TSI in this round would
be fabricated.

What will be computed, and reported under these names:

- **As (Affective Resonance)** — from GDELT tone/polarity. Fully specified.
- **Cw (Centrality Weight)** — graph centrality over GKG actor/entity
  co-occurrence. Resolves Open Item 1; algorithm justified in `tsi.py`.
- **Ts_proxy** — GKG-narrative vs Events-coded divergence. A **substitute**, not
  the specified Ts. The two products share an upstream provider and are not
  independent in the way ACLED and UCDP are. Reported separately and never
  silently folded into a headline TSI.
- **TSI_partial = Cw × As** — the two computable components, labelled as partial.
