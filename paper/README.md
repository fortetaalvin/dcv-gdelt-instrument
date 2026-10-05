# Manuscript

`methods-paper-v2.3.docx` — *Silent Failure Modes in GDELT-Based Crisis
Research: Twenty-Four Measured Defects and a Validation Protocol*, v2.3,
5 October 2026. `methods-paper-v2.3.html` is the same manuscript as served at
<https://dcv.forteta.ng/methods.html>.

Included so that §9's availability claim covers the manuscript as well as the
code and data. Every numbered defect in §4.2 is re-executable from
`../probes/boundary_probes.py`, and §5's fourteen checks are runnable from
`../protocol/validate.py`.

## Changes in v2.3

- **New defect §4.2.7.** A seventeen-day outage spanning 2025-06-14 to
  2025-07-02 is present in GKG v1, Events 1.0, GKG 2.0 and Events 2.0
  simultaneously. Found incidentally in September 2026 during unrelated work,
  re-probed 2026-10-04 and 2026-10-05 and still absent. This qualifies §4.2.3:
  cross-generation redundancy is a convenience, not an independent check, because
  the generations share upstream infrastructure.
- Defect count 23 to 24; protocol 13 steps to 14.
- **New protocol step 9** — probe for mid-window outages in every product you
  rely on, not only start-of-archive boundaries. It is automatable, so it is a
  runnable check (`check_9_known_outage`) rather than a manual one.
- `check_7_gaps` now cross-probes the current generation whenever it finds a
  missing day, and reports whether the gap is correlated or fillable.
- Ten new probes, `B5-a` through `B5-j`, including both boundary controls.
