# INDIA GHCNh audit (multi-city expansion)

Engineering audit, no marketing language. All numbers measured 2026-09-29
from repository files or NODD S3 HEAD probes. Repo-relative paths below
are under `Backend/` (the task's `data/...` means `Backend/data/...`).

## 1. Source

NOAA NCEI GHCNh v1.1.0 (updated 2026-03-10), DOI 10.25921/jp3d-3v19,
via NODD S3 `s3://noaa-ghcnh-pds`, prefix
`hourly/access/by-year/{year}/parquet/GHCNh_{station}_{year}.parquet`,
HTTPS read-only (existing `src/noaa/acquire.py`).

## 2. Dataset version

GHCNh v1.1.0. Existing 2022-2024 window untouched; this phase adds
2020/2021/2025 extension years (30 files, ~15 MB total).

## 3. Cities attempted

Mumbai, Hyderabad, Chennai, Bengaluru, Pune, Kolkata, Bhopal, Jaipur,
Lucknow, Chandigarh (all 10 task candidates).

## 4. Stations discovered

`data/india_station_discovery.csv` (10 PRIMARY, inventory-verified):
VABB/VOHS/VOMM/VOBL/VAPO/U042809-1/VABP/VIJP/VILK/VICG. All 10 target
cities already had 2022-2024 processed files; discovery confirms the
same stations extend to 2020/2021/2025.

## 5. Stations selected

PRIMARY only, one per city (list above). No SECONDARY: coverage is
adequate and duplicates add nothing.

## 6. Stations rejected

None rejected outright; Pune (69 extension rows) and Chandigarh (2435)
are sparse outside 2022-2024 — flagged, not forced. NO_SUITABLE_TPR
was not needed: every city has T+RH-rich data.

## 7. T/P/RH coverage (extension years)

T ~100%, RH ~100% everywhere. Station-level pressure ~0% (Bhopal 30.7%,
Chennai 17.0% partial). 2022-2024 processed files agree: station-level
pressure 0-0.5% (Bhopal 30.4%, Chennai 16.5%). Full table:
`data/processed/india_station_audit.csv`.

## 8. Joint coverage

Station-pressure joint TPR: 0-2% (Bhopal 30.7%) — below any FULL_TPR
bar. Altimeter-based joint T/P/RH: ~100% (altimeter ~98-100% all
stations). Pune/Chandigarh joint coverage is limited by row counts,
not missingness.

## 9. Pressure semantics

`pressure_variable_used = altimeter_setting_hpa` (QNH) wherever a
detector runs; `station_level_pressure` is recorded but ~absent.
`pressure_semantics`: QNH is a sea-level-reduced estimate, NOT station
pressure — never substituted silently, never mixed within a series.
Delhi-trained artifacts (station-pressure distributions) do NOT transfer.

## 10. RH provenance

`humidity_source = REPORTED (provider file)`. GHCNh ships a
`relative_humidity` column with provider QC codes; our pipeline reads
that column only (never dew point). Whether the provider measured or
computed it is NOT verifiable from bulk files — recorded as reported,
not claimed as sensor-measured.

## 11. Cadence

Median 30 min (Chandigarh 60 min in extension years; Pune sparse).
Source resolution: synoptic/sub-hourly station reports, NOT 5-min AWS.
UTC throughout; no resampling, no invented timestamps.

## 12. Missingness

Per-variable missing counts in the audit CSV; max joint-missing runs up
to tens of thousands of rows where pressure is absent (structural, not
random). T/RH missingness <0.2%.

## 13. Continuous segments

Extension files are continuous within years; cross-year and
pressure-gap boundaries must not be crossed by temporal windows
(segment logic in the feature builder enforces this).

## 14. Feature compatibility

| feature group | cadence | requires_tpr | compatible_hourly | action |
|---|---|---|---|---|
| horizons_for_cadence mapping | independent | no | yes | KEEP |
| causal rolling windows (30m/2h/6h) | time-based | yes | yes | KEEP |
| per-hour rates | independent | yes | yes | KEEP |
| hour/dayofyear cyclical | independent | no | yes | KEEP |
| gap/segment logic | time-based | no | yes | KEEP |
| multivariate deviations | independent | yes | yes | KEEP |
| ensemble combine policy | independent | no | yes | KEEP |
| statistical z=3/IQR flags | independent | yes | yes, uncalibrated | ADAPT (station calibration required) |
| Isolation Forest model+allowlist | Delhi-trained | yes | no | EXCLUDE_WITH_REASON (hourly validation required) |
| LSTM 12-step + scaler | Delhi-trained, 1h field | yes | no | EXCLUDE_WITH_REASON (hourly model required; NOT trained here) |
| root-cause classifier/SHAP | Delhi-trained | yes | no | EXCLUDE_WITH_REASON |

Verified: 106-column feature frame builds cleanly on 30-min Mumbai
data (`prepare_split` + `build_features_for_dataset` with
`cadence_min=30.0`).

## 15. Detector compatibility

Statistical baseline: RUNS on hourly data (validated §17 of coverage
doc); Delhi-fitted bands do not transfer (documented miscalibration).
IF/LSTM/RC: excluded pending hourly validation/training (STOP gate).

## 16. Final capability classification

All 10: PARTIAL (T+RH rich, altimeter pressure, statistical response
demonstrated, uncalibrated). Zero FULL_TPR. Zero CONTEXT_ONLY (all have
detector-path evidence). Zero UNAVAILABLE.

## 17. Validation results

Mumbai March-2023, 1440 rows, 4 injected faults, frozen z=3/IQR:
spike 1.0, frozen 0.5, drift 0.5, cross-variable 1.0; overall P 0.19 /
R 0.50. High FP rate is the Delhi-calibration mismatch (IQR bands),
reported as found. Metrics: `reports/india_ghcnh/mumbai_statistical_validation.json`.

## 18. Known limitations

Station pressure absent (altimeter only); RH reported-not-verified;
Delhi calibration does not transfer (new stations need own
calibration/training — future work); Pune/Chandigarh sparse outside
2022-2024; replay wiring and OOD eval of new models deferred;
serving APIs/UI unchanged (Delhi-only serving preserved).
