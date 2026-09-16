# Instrument repair — keyword sets v3

**Stamped 2026-09-16, before re-running any case.**

Round 2's audit found that descriptive multi-word keywords match nothing in
GDELT GKG: the field holds named entities and theme codes, not prose. Between
one and three terms of every four-term set were inert, and #EndBadGovernance ran
on a single live term. This repairs the instrument.

## Repair rule (mechanical)

1. **Every live term is kept unchanged.** No live term is added, removed, or
   reweighted. Whatever the repaired sets do, they cannot be accused of tuning
   the terms that were already working.
2. **Each dead term is replaced by the GKG theme code that most directly names
   the same concept the dead term named.** The mapping is made from the theme
   vocabulary, not from detection results.
3. **Every term is validated to return > 0 records before the run.** A dead term
   now raises an error instead of silently contributing nothing. This is the
   defect that produced the round-2 #EndBadGovernance null.

Dropping a dead term cannot change any number — it matched zero records by
definition — so step 1 is verifiable rather than merely asserted.

## The mapping

| Case | Dead term | Replaced by | Why |
|---|---|---|---|
| chibok_2014 | `schoolgirls abduction` | `KIDNAP` | names abduction |
| endsars_2020 | `SARS Nigeria` | `SECURITY_SERVICES` | SARS was a police unit |
| endsars_2020 | `police brutality Nigeria` | `UNREST_POLICEBRUTALITY` | exact concept match |
| kankara_2020 | `schoolboys abduction` | `KIDNAP` | names abduction |
| plateau_2018 | `herder farmer` | `ARMEDCONFLICT` | see caveat below |
| election_2023 | `election protest` | `PROTEST` | names protest |
| election_2023 | `presidential election Nigeria` | `ELECTION` | names election |
| endbadgov_2024 | `hunger protest` | `PROTEST` | names protest |
| endbadgov_2024 | `Nigeria protest` | `PROTEST` (dedup) | same code |
| endbadgov_2024 | `fuel subsidy` | `ECON_INFLATION` | nearest economic-trigger code |

**Caveat on Plateau.** GKG has no communal-violence theme. Its `TAX_ETHNICITY_*`
codes are nationality labels (`_AMERICAN`, `_CHINESE`), useless here.
`ARMEDCONFLICT` is broader than "herder farmer" and will over-match. This is the
weakest substitution in the table and is flagged rather than smoothed over.

**Caveat on #EndBadGovernance.** Two dead terms map to the same code, so the
repaired set has three terms, not four. Set sizes are not equalised — padding
them to four would mean inventing a term, which is exactly the tuning step 1
forbids.

## What this repair can and cannot test

**It cannot test group discrimination.** The dead terms in clandestine cases
named abduction concepts and those in mobilisational cases named protest
concepts, so a faithful translation necessarily gives `KIDNAP`-family codes to
one group and `PROTEST`-family codes to the other. A channel built that way
separates the groups *by construction*, and any accuracy figure from it would be
circular. **No discrimination claim will be made from the repaired narrative
channel.**

**It can test within-case lead time**: does a case's own signal rise before its
own trigger? That question is unaffected by the circularity, because the
comparison is against the case's own baseline, not against the other group.

The discrimination finding stays where round 2 left it — with the GDELT Events
protest-event channel, which uses no keywords and is untouched by this repair.

## Predictions

Stated before running, so the repair can fail visibly:

1. **#EndBadGovernance will now fire before its trigger.** Round 2's null there
   was attributed to instrument failure (one live term). If it still does not
   fire with three live terms, that attribution was wrong and the case is a
   genuine miss for the mobilisational account.
2. **Chibok will still not fire early.** Adding `KIDNAP` should raise the
   post-trigger series enormously and the pre-trigger series barely. If Chibok
   now fires early, the round-1 headline result was an artifact of keyword
   choice and must be withdrawn.
3. **Kankara will still fire early**, because its false positive came from
   `Katsina`/`Kankara` prior salience, which the repair does not touch.
4. **Cw for #EndBadGovernance will become non-zero**, since theme codes appear
   in the theme field — though Cw is computed over *entities*, so this may not
   follow, and if it does not, Cw's chance-level performance stands unexplained.

## Method otherwise unchanged

Same windows, same corpora (no re-ingestion — the repair is a re-filter of data
already retrieved), same detection rule, same 12-cell sweep. Round-2 results are
retained for side-by-side comparison; nothing is overwritten.
