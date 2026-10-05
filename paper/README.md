# Manuscript

`methods-paper-v2.3.docx` — *Silent Failure Modes in GDELT-Based Crisis
Research: Twenty-Three Measured Defects and a Validation Protocol*, v2.3,
5 October 2026. `methods-paper-v2.3.html` is the same manuscript as served at
<https://dcv.forteta.ng/methods.html>.

Included so that §9's availability claim covers the manuscript as well as the
code and data. Every numbered defect in §4.2 is re-executable from
`../probes/boundary_probes.py`, and §5's thirteen checks are runnable from
`../protocol/validate.py`.

## Changes in v2.3

One sentence, in §4.2.3. That section concluded that archive gaps differ between
GDELT's product generations and that the resulting redundancy performs unintended
preservation work. It now records that the redundancy is a convenience rather
than a guarantee, because a multi-day outage has since been observed absent from
GKG v1, Events 1.0, GKG 2.0 and Events 2.0 simultaneously — where generations
share upstream infrastructure, a second GDELT product is not an independent check
on the first.

The defect count stays at twenty-three and the protocol at thirteen steps. The
outage measurement is deliberately **not** folded into the paper; it is held for a
short data note of its own and is preserved, dated and re-executable at
`../probes/outage_2025.py`. A reviewer re-running `../probes/boundary_probes.py`
therefore gets exactly the claims this paper makes, and nothing else.
