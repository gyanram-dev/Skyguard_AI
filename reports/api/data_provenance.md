# Data Provenance (Phase 12 API)

The API reads frozen artifacts only; it writes nothing to data/ or
models/ and modifies no Phase 1–11 artifact.

## Sources

- Jena/Delhi observations: `data/processed/{jena,delhi}_clean.csv`
  (historical replay; Delhi timestamps are IST as stored).
- Ensemble scores/flags: `data/ensemble/{jena,delhi}_ensemble_predictions.csv`
  (frozen Phase 10; `ens_median` is the operational method).
- Diagnosis: `data/root_cause/{jena,delhi}_root_cause_predictions.csv`
  (frozen Phase 11; confidence is classifier confidence, null when absent).
- Events: `reports/ensemble/{jena,delhi}_event_results.csv` (detected
  ID/OOD events) + `reports/root_cause/end_to_end_diagnosis.csv`.
- NOAA context: `data/noaa/processed/spatial_consistency.csv`,
  `data/noaa/processed/{station}_2022_2024.csv`, Phase 8B AWS validation
  (Delhi investigation only, contextual, never ground truth).
- Mapping: `data/api/station_mapping.json` (frontend ↔ backend IDs with
  justification notes; AMD-06/HYD-07 explicitly offline).

## Models loaded at startup

IF joblibs, LSTM keras + scalers, ensemble calibration joblibs,
root-cause joblibs + TreeExplainer joblibs (all frozen). Statistical
baseline is rule logic (no artifact; always available).

## Known unavailable data

- AMD-06 (Ahmedabad), HYD-07 (Hyderabad): no backend dataset → 404/offline.
- NOAA stations: no ensemble detector → anomaly `detected: false`,
  spatial score surfaced without flags.
- Guwahati/Trivandrum/Safdarjung NOAA stations: no frontend mock ID, not
  served (documented in mapping notes via omission).
- History outside dataset ranges returns only available points.
- Nothing here is live weather; all values are historical replay.
