# Traditional Statistical QC Baseline — Benchmark Evaluation: Phase 6

**Project**: SIH 2026 PS 26073. **Scope**: evaluate the FROZEN Phase 4 baseline only.
All numbers below describe the Traditional Statistical QC Baseline — no SkyGuard ML exists yet.
Benchmark signal: recomputed causally per split (Phase 3 features + Phase 2.5 quality + Phase 4 flags).
Background rows are non-injected background observations, NOT proven normal.

## Metric equations

Precision = TP/(TP+FP); Recall = TP/(TP+FN); F1 = 2PR/(P+R); FPR = FP/(FP+TN); FNR = FN/(TP+FN). Zero denominators → NaN.

## Jena — communication gaps: 60 events (DATA_QUALITY responsible; gap intervals contain no rows; excluded from row metrics).
## Delhi — communication gaps: 60 events (DATA_QUALITY responsible; gap intervals contain no rows; excluded from row metrics).

## Overall row metrics (eligible rows, official thresholds |z|>3.0, 1.5×IQR)

| Dataset | Split | Method | Precision | Recall | F1 | FPR | FNR |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | train | zscore | 0.0120 | 0.1988 | 0.0226 | 0.1266 | 0.8012 |
| jena | train | iqr | 0.0090 | 0.3970 | 0.0177 | 0.3366 | 0.6030 |
| jena | train | combined | 0.0090 | 0.4001 | 0.0176 | 0.3404 | 0.5999 |
| jena | test_in_distribution | zscore | 0.0324 | 0.1701 | 0.0544 | 0.1252 | 0.8299 |
| jena | test_in_distribution | iqr | 0.0261 | 0.3639 | 0.0487 | 0.3347 | 0.6361 |
| jena | test_in_distribution | combined | 0.0262 | 0.3694 | 0.0489 | 0.3386 | 0.6306 |
| jena | test_generalization | zscore | 0.0515 | 0.1827 | 0.0804 | 0.1277 | 0.8173 |
| jena | test_generalization | iqr | 0.0389 | 0.3614 | 0.0703 | 0.3388 | 0.6386 |
| jena | test_generalization | combined | 0.0388 | 0.3646 | 0.0702 | 0.3429 | 0.6354 |
| delhi | train | zscore | 0.0275 | 0.1294 | 0.0454 | 0.0970 | 0.8706 |
| delhi | train | iqr | 0.0226 | 0.2774 | 0.0418 | 0.2544 | 0.7226 |
| delhi | train | combined | 0.0226 | 0.2805 | 0.0419 | 0.2572 | 0.7195 |
| delhi | test_in_distribution | zscore | 0.0915 | 0.1395 | 0.1105 | 0.0913 | 0.8605 |
| delhi | test_in_distribution | iqr | 0.0746 | 0.2972 | 0.1192 | 0.2431 | 0.7028 |
| delhi | test_in_distribution | combined | 0.0750 | 0.3017 | 0.1201 | 0.2454 | 0.6983 |
| delhi | test_generalization | zscore | 0.1131 | 0.1431 | 0.1264 | 0.1074 | 0.8569 |
| delhi | test_generalization | iqr | 0.0985 | 0.2913 | 0.1473 | 0.2551 | 0.7087 |
| delhi | test_generalization | combined | 0.0986 | 0.2945 | 0.1477 | 0.2578 | 0.7055 |

## Event recall + latency (median/mean/min/max minutes)

| Dataset | Split | Method | Events | Detected | Recall | Lat med | Lat mean | Lat min | Lat max |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| jena | train | zscore | 120 | 97 | 0.8083 | 0.0000 | 19.7938 | 0.0000 | 150.0000 |
| jena | train | iqr | 120 | 108 | 0.9000 | 0.0000 | 12.5000 | 0.0000 | 150.0000 |
| jena | train | combined | 120 | 108 | 0.9000 | 0.0000 | 12.4074 | 0.0000 | 150.0000 |
| jena | test_in_distribution | zscore | 120 | 91 | 0.7583 | 0.0000 | 22.3077 | 0.0000 | 320.0000 |
| jena | test_in_distribution | iqr | 120 | 110 | 0.9167 | 0.0000 | 12.5455 | 0.0000 | 120.0000 |
| jena | test_in_distribution | combined | 120 | 110 | 0.9167 | 0.0000 | 12.0000 | 0.0000 | 120.0000 |
| jena | test_generalization | zscore | 140 | 132 | 0.9429 | 10.0000 | 33.2576 | 0.0000 | 360.0000 |
| jena | test_generalization | iqr | 140 | 139 | 0.9929 | 0.0000 | 15.5396 | 0.0000 | 130.0000 |
| jena | test_generalization | combined | 140 | 139 | 0.9929 | 0.0000 | 15.5396 | 0.0000 | 130.0000 |
| delhi | train | zscore | 120 | 89 | 0.7417 | 0.0000 | 29.2135 | 0.0000 | 410.0000 |
| delhi | train | iqr | 120 | 97 | 0.8083 | 0.0000 | 17.3196 | 0.0000 | 220.0000 |
| delhi | train | combined | 120 | 99 | 0.8250 | 0.0000 | 17.1212 | 0.0000 | 220.0000 |
| delhi | test_in_distribution | zscore | 120 | 80 | 0.6667 | 5.0000 | 37.8750 | 0.0000 | 380.0000 |
| delhi | test_in_distribution | iqr | 120 | 96 | 0.8000 | 0.0000 | 17.2917 | 0.0000 | 380.0000 |
| delhi | test_in_distribution | combined | 120 | 96 | 0.8000 | 0.0000 | 16.9792 | 0.0000 | 380.0000 |
| delhi | test_generalization | zscore | 140 | 115 | 0.8214 | 5.0000 | 37.6957 | 0.0000 | 385.0000 |
| delhi | test_generalization | iqr | 140 | 126 | 0.9000 | 0.0000 | 16.2698 | 0.0000 | 205.0000 |
| delhi | test_generalization | combined | 140 | 126 | 0.9000 | 0.0000 | 15.8333 | 0.0000 | 205.0000 |

## Per-fault recall (row level, ID vs OOD)

| Dataset | Split | Fault | Z recall | IQR recall | Comb recall | Z event | IQR event | Comb event |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| jena | train | SPIKE | 0.8621 | 0.9828 | 0.9828 | 0.9667 | 0.9667 | 0.9667 |
| jena | train | FROZEN | 0.1093 | 0.2514 | 0.2514 | 0.2667 | 0.6333 | 0.6333 |
| jena | train | DRIFT | 0.1350 | 0.3358 | 0.3398 | 1.0000 | 1.0000 | 1.0000 |
| jena | train | CROSS_VARIABLE | 0.5936 | 0.8503 | 0.8503 | 1.0000 | 1.0000 | 1.0000 |
| jena | test_in_distribution | SPIKE | 0.8704 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| jena | test_in_distribution | FROZEN | 0.1444 | 0.3167 | 0.3222 | 0.3667 | 0.7000 | 0.7000 |
| jena | test_in_distribution | DRIFT | 0.1198 | 0.3077 | 0.3134 | 0.9333 | 1.0000 | 1.0000 |
| jena | test_in_distribution | CROSS_VARIABLE | 0.4061 | 0.6853 | 0.6904 | 0.7333 | 0.9667 | 0.9667 |
| jena | test_generalization | SPIKE | 0.8667 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| jena | test_generalization | FROZEN | 0.1054 | 0.2753 | 0.2796 | 0.8000 | 0.9667 | 0.9667 |
| jena | test_generalization | DRIFT | 0.1571 | 0.3515 | 0.3563 | 0.9667 | 1.0000 | 1.0000 |
| jena | test_generalization | CROSS_VARIABLE | 0.2419 | 0.3911 | 0.3928 | 0.9667 | 1.0000 | 1.0000 |
| jena | test_generalization | SPIKE_PLUS_DRIFT | 0.1883 | 0.3810 | 0.3825 | 1.0000 | 1.0000 | 1.0000 |
| delhi | train | SPIKE | 0.9298 | 0.9298 | 0.9298 | 0.9333 | 0.9333 | 0.9333 |
| delhi | train | FROZEN | 0.0939 | 0.2541 | 0.2597 | 0.2667 | 0.4333 | 0.4667 |
| delhi | train | DRIFT | 0.0896 | 0.2394 | 0.2423 | 0.9333 | 0.9667 | 1.0000 |
| delhi | train | CROSS_VARIABLE | 0.5968 | 0.7473 | 0.7527 | 0.8333 | 0.9000 | 0.9000 |
| delhi | test_in_distribution | SPIKE | 0.8276 | 0.9138 | 0.9138 | 0.8667 | 0.9000 | 0.9000 |
| delhi | test_in_distribution | FROZEN | 0.0444 | 0.1500 | 0.1500 | 0.1333 | 0.4000 | 0.4000 |
| delhi | test_in_distribution | DRIFT | 0.1134 | 0.2741 | 0.2772 | 0.9667 | 1.0000 | 1.0000 |
| delhi | test_in_distribution | CROSS_VARIABLE | 0.4545 | 0.6364 | 0.6684 | 0.7000 | 0.9000 | 0.9000 |
| delhi | test_generalization | SPIKE | 0.9403 | 0.9701 | 0.9701 | 0.9000 | 0.9667 | 0.9667 |
| delhi | test_generalization | FROZEN | 0.0789 | 0.1491 | 0.1506 | 0.3333 | 0.5667 | 0.5667 |
| delhi | test_generalization | DRIFT | 0.0983 | 0.2557 | 0.2576 | 0.9667 | 1.0000 | 1.0000 |
| delhi | test_generalization | CROSS_VARIABLE | 0.3847 | 0.5771 | 0.5854 | 0.9667 | 1.0000 | 1.0000 |
| delhi | test_generalization | SPIKE_PLUS_DRIFT | 0.1026 | 0.2608 | 0.2647 | 1.0000 | 1.0000 | 1.0000 |

## SPIKE_PLUS_DRIFT (OOD only, unseen combination)

- jena/zscore: 20/20 events, event recall 1.0000, row recall 0.1883.
- jena/iqr: 20/20 events, event recall 1.0000, row recall 0.3810.
- jena/combined: 20/20 events, event recall 1.0000, row recall 0.3825.
- delhi/zscore: 20/20 events, event recall 1.0000, row recall 0.1026.
- delhi/iqr: 20/20 events, event recall 1.0000, row recall 0.2608.
- delhi/combined: 20/20 events, event recall 1.0000, row recall 0.2647.

## False-positive analysis (eligible background rows only)

| Dataset | Split | Method | Background rows | FP count | FP rate | FP per 10k |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| jena | train | zscore | 250015 | 31663 | 0.1266 | 1266.4440 |
| jena | train | iqr | 250015 | 84145 | 0.3366 | 3365.5981 |
| jena | train | combined | 250015 | 85113 | 0.3404 | 3404.3157 |
| jena | test_in_distribution | zscore | 81856 | 10252 | 0.1252 | 1252.4433 |
| jena | test_in_distribution | iqr | 81856 | 27394 | 0.3347 | 3346.6087 |
| jena | test_in_distribution | combined | 81856 | 27716 | 0.3386 | 3385.9461 |
| jena | test_generalization | zscore | 80455 | 10275 | 0.1277 | 1277.1114 |
| jena | test_generalization | iqr | 80455 | 27255 | 0.3388 | 3387.6080 |
| jena | test_generalization | combined | 80455 | 27586 | 0.3429 | 3428.7490 |
| delhi | train | zscore | 169292 | 16418 | 0.0970 | 969.8037 |
| delhi | train | iqr | 169292 | 43071 | 0.2544 | 2544.1840 |
| delhi | train | combined | 169292 | 43534 | 0.2572 | 2571.5332 |
| delhi | test_in_distribution | zscore | 54059 | 4933 | 0.0913 | 912.5215 |
| delhi | test_in_distribution | iqr | 54059 | 13140 | 0.2431 | 2430.6776 |
| delhi | test_in_distribution | combined | 54059 | 13265 | 0.2454 | 2453.8005 |
| delhi | test_generalization | zscore | 51825 | 5566 | 0.1074 | 1073.9990 |
| delhi | test_generalization | iqr | 51825 | 13220 | 0.2551 | 2550.8924 |
| delhi | test_generalization | combined | 51825 | 13363 | 0.2578 | 2578.4853 |

Descriptive only: common FP patterns are single-variable IQR excursions on smooth diurnal segments; no root causes are invented. Full per-variable breakdown in `false_positive_analysis.csv`.

## ID vs OOD generalization (delta = OOD − ID)

| Dataset | Method | ID F1 | OOD F1 | ΔF1 | ID recall | OOD recall | Δrecall | ID event rec | OOD event rec |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| jena | zscore | 0.0544 | 0.0804 | 0.0260 | 0.1701 | 0.1827 | 0.0126 | 0.7583 | 0.9429 |
| jena | iqr | 0.0487 | 0.0703 | 0.0216 | 0.3639 | 0.3614 | -0.0025 | 0.9167 | 0.9929 |
| jena | combined | 0.0489 | 0.0702 | 0.0213 | 0.3694 | 0.3646 | -0.0047 | 0.9167 | 0.9929 |
| delhi | zscore | 0.1105 | 0.1264 | 0.0158 | 0.1395 | 0.1431 | 0.0036 | 0.6667 | 0.8214 |
| delhi | iqr | 0.1192 | 0.1473 | 0.0280 | 0.2972 | 0.2913 | -0.0059 | 0.8000 | 0.9000 |
| delhi | combined | 0.1201 | 0.1477 | 0.0276 | 0.3017 | 0.2945 | -0.0072 | 0.8000 | 0.9000 |

## Threshold diagnostics (sensitivity only; official settings unchanged)

| Dataset | Split | Method | Threshold | Precision | Recall | FPR |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| jena | train | zscore | 2.0 | 0.0085 | 0.5833 | 0.5247 |
| jena | train | zscore | 2.5 | 0.0103 | 0.3473 | 0.2586 |
| jena | train | zscore | 3.0 | 0.0120 | 0.1988 | 0.1266 |
| jena | train | zscore | 3.5 | 0.0123 | 0.1030 | 0.0639 |
| jena | train | zscore | 4.0 | 0.0147 | 0.0663 | 0.0344 |
| jena | train | iqr | 1.0 | 0.0084 | 0.5916 | 0.5411 |
| jena | train | iqr | 1.5 | 0.0090 | 0.3970 | 0.3366 |
| jena | train | iqr | 2.0 | 0.0096 | 0.2764 | 0.2198 |
| jena | train | iqr | 2.5 | 0.0107 | 0.2096 | 0.1503 |
| jena | test_in_distribution | zscore | 2.0 | 0.0263 | 0.5736 | 0.5232 |
| jena | test_in_distribution | zscore | 2.5 | 0.0293 | 0.3123 | 0.2546 |
| jena | test_in_distribution | zscore | 3.0 | 0.0324 | 0.1701 | 0.1252 |
| jena | test_in_distribution | zscore | 3.5 | 0.0347 | 0.0922 | 0.0633 |
| jena | test_in_distribution | zscore | 4.0 | 0.0399 | 0.0590 | 0.0350 |
| jena | test_in_distribution | iqr | 1.0 | 0.0254 | 0.5741 | 0.5426 |
| jena | test_in_distribution | iqr | 1.5 | 0.0261 | 0.3639 | 0.3347 |
| jena | test_in_distribution | iqr | 2.0 | 0.0292 | 0.2667 | 0.2187 |
| jena | test_in_distribution | iqr | 2.5 | 0.0300 | 0.1879 | 0.1497 |
| jena | test_generalization | zscore | 2.0 | 0.0400 | 0.5686 | 0.5177 |
| jena | test_generalization | zscore | 2.5 | 0.0433 | 0.3061 | 0.2569 |
| jena | test_generalization | zscore | 3.0 | 0.0515 | 0.1827 | 0.1277 |
| jena | test_generalization | zscore | 3.5 | 0.0581 | 0.1064 | 0.0655 |
| jena | test_generalization | zscore | 4.0 | 0.0682 | 0.0694 | 0.0360 |
| jena | test_generalization | iqr | 1.0 | 0.0377 | 0.5538 | 0.5368 |
| jena | test_generalization | iqr | 1.5 | 0.0389 | 0.3614 | 0.3388 |
| jena | test_generalization | iqr | 2.0 | 0.0424 | 0.2589 | 0.2221 |
| jena | test_generalization | iqr | 2.5 | 0.0472 | 0.1990 | 0.1524 |
| delhi | train | zscore | 2.0 | 0.0227 | 0.4908 | 0.4493 |
| delhi | train | zscore | 2.5 | 0.0230 | 0.2323 | 0.2091 |
| delhi | train | zscore | 3.0 | 0.0275 | 0.1294 | 0.0970 |
| delhi | train | zscore | 3.5 | 0.0315 | 0.0698 | 0.0455 |
| delhi | train | zscore | 4.0 | 0.0372 | 0.0417 | 0.0229 |
| delhi | train | iqr | 1.0 | 0.0223 | 0.4566 | 0.4252 |
| delhi | train | iqr | 1.5 | 0.0226 | 0.2774 | 0.2544 |
| delhi | train | iqr | 2.0 | 0.0238 | 0.1898 | 0.1651 |
| delhi | train | iqr | 2.5 | 0.0255 | 0.1397 | 0.1132 |
| delhi | test_in_distribution | zscore | 2.0 | 0.0734 | 0.5102 | 0.4246 |
| delhi | test_in_distribution | zscore | 2.5 | 0.0800 | 0.2605 | 0.1974 |
| delhi | test_in_distribution | zscore | 3.0 | 0.0915 | 0.1395 | 0.0913 |
| delhi | test_in_distribution | zscore | 3.5 | 0.1008 | 0.0713 | 0.0419 |
| delhi | test_in_distribution | zscore | 4.0 | 0.1137 | 0.0410 | 0.0211 |
| delhi | test_in_distribution | iqr | 1.0 | 0.0700 | 0.4608 | 0.4037 |
| delhi | test_in_distribution | iqr | 1.5 | 0.0746 | 0.2972 | 0.2431 |
| delhi | test_in_distribution | iqr | 2.0 | 0.0739 | 0.1903 | 0.1571 |
| delhi | test_in_distribution | iqr | 2.5 | 0.0803 | 0.1440 | 0.1086 |
| delhi | test_generalization | zscore | 2.0 | 0.1047 | 0.5144 | 0.4212 |
| delhi | test_generalization | zscore | 2.5 | 0.1071 | 0.2631 | 0.2099 |
| delhi | test_generalization | zscore | 3.0 | 0.1131 | 0.1431 | 0.1074 |
| delhi | test_generalization | zscore | 3.5 | 0.1199 | 0.0786 | 0.0552 |
| delhi | test_generalization | zscore | 4.0 | 0.1381 | 0.0518 | 0.0310 |
| delhi | test_generalization | iqr | 1.0 | 0.0974 | 0.4556 | 0.4042 |
| delhi | test_generalization | iqr | 1.5 | 0.0985 | 0.2913 | 0.2551 |
| delhi | test_generalization | iqr | 2.0 | 0.1026 | 0.2074 | 0.1737 |
| delhi | test_generalization | iqr | 2.5 | 0.1036 | 0.1524 | 0.1262 |

## Limitations and reproduction

- Background flag rates use non-injected background (not guaranteed clean).
- Thresholds were NOT tuned; OOD was NOT used for selection; Phase 4 untouched.
- No pressure/temperature hard rules exist in this path (verified by Phase 4/5 tests); 55 °C is flaggable only by statistical context, never deleted.
- Command: `python -m src.evaluation.statistical_baseline.run` (deterministic; timing excluded).
