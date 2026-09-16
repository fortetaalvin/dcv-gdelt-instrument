# Data files

## `provenance.sqlite` (2.19 MB)

The audit trail. Three tables, no raw GDELT content.

| Table | Rows | Contents |
|---|---|---|
| `pulls` | 4,943 | One row per retrieval: `endpoint`, `params_json`, `http_status`, `record_count`, `response_sha256`, `outcome`, `started_at`, `finished_at` |
| `cases` | 13 | Versioned case specifications: **12** are six cases x two keyword versions; the thirteenth (`nigeria_continuous`) is a provenance holder for the continuous pull, not a case. A keyword revision creates a new version rather than mutating the old one |
| `daily_counts` | 4,009 | Daily aggregates for Nigeria, 2014-01-01 to 2024-12-31: total, protest, conflict, fight and assault event counts, mention-weighted Goldstein numerator/denominator, tone sum and n |

`outcome` is one of `success`, `empty`, `rejected`, `rate_limited`, `error`.
Failures are rows, not omissions: 4,918 succeeded, 13 were rejected (archive
gaps), 7 errored, 4 were rate-limited.

Useful queries:

```sql
-- every retrieval behind one case
SELECT p.endpoint, p.params_json, p.response_sha256, p.outcome
FROM pulls p JOIN cases c ON c.case_id = p.case_id
WHERE c.slug = 'chibok_2014';

-- the archive gaps reported in methods paper §4.2.3
SELECT source_platform, params_json, error_detail
FROM pulls WHERE outcome = 'rejected';

-- archive non-stationarity, §4.2.4
SELECT substr(day,1,4) AS year, ROUND(AVG(total_events),1) AS events_per_day
FROM daily_counts GROUP BY year ORDER BY year;
```

Note `daily_counts` stores Goldstein as numerator and denominator rather than a
mean, so that days can be aggregated correctly: a mean of daily means is not the
mention-weighted mean over a period.

## Analysis outputs

| File | Produced by | Contents |
|---|---|---|
| `round2.json` | `scripts/run_round2.py` | Six-case detection, all channels, full 12-cell parameter surface |
| `round3.json` | `scripts/run_round3.py` | Same after keyword repair (v2 specifications) |
| `liveonly.json` | inline variant | Live-terms-only control; reproduces round 2 to the decimal, proving dead terms inert (§4.1.4) |
| `round4.json` | `scripts/round4.py` | Continuous rolling detection over 4,009 days, eight parameter settings |
| `rolling.json` | `dcv/rolling.py` | Prospective evaluation per case |
| `linkrot.json` | `scripts/linkrot.py` | 1,200 URLs: resolution outcome, status, domain. `wayback` is `null` throughout — see below |
| `dashboard.json` | `scripts/compute_all.py` | Every construct for all six cases plus the continuous series |

### `linkrot.json` — why `wayback` is null

The field is `null` for every dead URL, deliberately. Our first pass issued
twelve concurrent requests to archive.org, which returned HTTP 429 to all of
them; scoring those as "not archived" would have made the field a measurement of
our own request rate. A serial re-run at 1.6-second pacing was still refused.
The placeholder values were overwritten with `null` rather than left in place,
and the paper reports no recoverability figure.

The resolution results themselves are unaffected — those queried the source
domains directly, not archive.org.

## Not included

Raw GDELT records (3.34M rows, ~8 GB). See the root README for why, and use
`pulls` to re-execute any retrieval.
