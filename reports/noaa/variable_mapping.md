# NOAA → SkyGuard Variable Mapping (Phase 8A)

Source: Global Historical Climatology Network hourly (GHCNh) 1.1.0 (updated 2026-03-10).
Timestamps are UTC (`timestamp_utc`). Missing values are empty (NaN); the provider -9999 sentinel is mapped to NaN, never imputed.

| SkyGuard field | GHCNh source field | Unit | Role | Note |
| :--- | :--- | :--- | :--- | :--- |
| temperature_c | temperature | degC | primary | Dry-bulb air temperature. |
| station_level_pressure_hpa | station_level_pressure | hPa | primary | True barometric pressure at station elevation. Sparse at METAR-fed stations; absent values stay missing, never filled. |
| sea_level_pressure_hpa | sea_level_pressure | hPa | primary | Reduction estimate to sea level using the station temperature profile. Documented as-is; NOT station pressure. |
| altimeter_setting_hpa | altimeter | hPa | auxiliary | QNH reduced with the standard atmosphere. Universally reported; candidate common pressure basis for Phase 8B, undecided here. |
| relative_humidity_pct | relative_humidity | percent | primary | Natively reported; no derivation needed. |
| dew_point_temperature_c | dew_point_temperature | degC | humidity-equivalent | Defensible humidity-equivalent backup where RH is missing; no RH is manufactured from it in this phase. |

Pressure discipline: `station_level_pressure` is the true barometric pressure at station elevation; `sea_level_pressure` is a reduction estimate, never substituted for station pressure; `altimeter_setting_hpa` (QNH, hPa) is auxiliary. The Phase 8B common-pressure basis is undecided in this phase.

Per-station variable availability is recorded in `station_selection.csv` (`available_variables`).
