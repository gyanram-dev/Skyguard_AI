# Freeze detector — frozen benchmark evaluation

Generated: 2026-09-30T07:38:34.094774+00:00

Rule: min_run_rows=6; variables=['temperature', 'pressure', 'relative humidity']; exclusion=relative humidity at 0/100 (saturation) is never a freeze; causal=a row is flagged only when its own observed run reaches the threshold; gap_semantics=NaN and communication-gap rows terminate runs; severity=LOW (>=6) < MEDIUM (>=12) < HIGH (>= 6-hour DQ row count); confidence=run/(run+6) evidence-strength margin, not a probability

Chosen threshold: **6 consecutive identical readings**.

## Threshold sweep (FROZEN event recall vs added background flags)

| reads | dataset | split | FROZEN events | ens_median | + freeze | added bg rows | bg FP/10k |
|---|---|---|---|---|---|---|---|
| 4 | delhi | test_in_distribution | 30 | 2 | 27 | 0 | 239.37 -> 239.37 |
| 4 | delhi | test_generalization | 30 | 5 | 29 | 0 | 349.83 -> 349.83 |
| 4 | jena | test_in_distribution | 30 | 3 | 24 | 928 | 129.37 -> 242.74 |
| 4 | jena | test_generalization | 30 | 11 | 30 | 560 | 168.42 -> 238.02 |
| 5 | delhi | test_in_distribution | 30 | 2 | 22 | 0 | 239.37 -> 239.37 |
| 5 | delhi | test_generalization | 30 | 5 | 29 | 0 | 349.83 -> 349.83 |
| 5 | jena | test_in_distribution | 30 | 3 | 21 | 443 | 129.37 -> 183.49 |
| 5 | jena | test_generalization | 30 | 11 | 30 | 227 | 168.42 -> 196.63 |
| 6 | delhi | test_in_distribution | 30 | 2 | 19 | 0 | 239.37 -> 239.37 |
| 6 | delhi | test_generalization | 30 | 5 | 29 | 0 | 349.83 -> 349.83 |
| 6 | jena | test_in_distribution | 30 | 3 | 17 | 256 | 129.37 -> 160.65 |
| 6 | jena | test_generalization | 30 | 11 | 30 | 102 | 168.42 -> 181.1 |

## Chosen threshold (6) details

### delhi/test_in_distribution

- eligible rows: 57622, background rows: 54059
- baseline: 1294 background flags (239.37/10k)
- combined: 1294 background flags (239.37/10k), added 0 rows

| fault | events | ens_median detected | freeze rule detected | combined |
|---|---|---|---|---|
| SPIKE | 30 | 27 | 0 | 27 |
| FROZEN | 30 | 2 | 17 | 19 |
| DRIFT | 30 | 16 | 0 | 16 |
| CROSS_VARIABLE | 30 | 17 | 0 | 17 |

### delhi/test_generalization

- eligible rows: 56786, background rows: 51825
- baseline: 1813 background flags (349.83/10k)
- combined: 1813 background flags (349.83/10k), added 0 rows

| fault | events | ens_median detected | freeze rule detected | combined |
|---|---|---|---|---|
| SPIKE | 30 | 29 | 0 | 29 |
| FROZEN | 30 | 5 | 29 | 29 |
| DRIFT | 30 | 10 | 0 | 10 |
| CROSS_VARIABLE | 30 | 30 | 0 | 30 |
| SPIKE_PLUS_DRIFT | 20 | 20 | 0 | 20 |

### jena/test_in_distribution

- eligible rows: 83873, background rows: 81856
- baseline: 1059 background flags (129.37/10k)
- combined: 1315 background flags (160.65/10k), added 256 rows

| fault | events | ens_median detected | freeze rule detected | combined |
|---|---|---|---|---|
| SPIKE | 30 | 30 | 0 | 30 |
| FROZEN | 30 | 3 | 16 | 17 |
| DRIFT | 30 | 10 | 0 | 10 |
| CROSS_VARIABLE | 30 | 12 | 0 | 12 |

### jena/test_generalization

- eligible rows: 83510, background rows: 80455
- baseline: 1355 background flags (168.42/10k)
- combined: 1457 background flags (181.1/10k), added 102 rows

| fault | events | ens_median detected | freeze rule detected | combined |
|---|---|---|---|---|
| SPIKE | 30 | 30 | 0 | 30 |
| FROZEN | 30 | 11 | 30 | 30 |
| DRIFT | 30 | 16 | 1 | 16 |
| CROSS_VARIABLE | 30 | 30 | 0 | 30 |
| SPIKE_PLUS_DRIFT | 20 | 20 | 0 | 20 |

Notes: predictions are the frozen record of the published benchmark run; the freeze rule is applied post hoc exactly as in serving. Events count an injection as detected when any eligible row inside its window is flagged. Controlled injections are synthetic labels, not real sensor faults.
