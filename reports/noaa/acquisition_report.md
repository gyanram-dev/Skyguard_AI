# NOAA Multi-Station Acquisition + Audit (Phase 8A)

Dataset: **Global Historical Climatology Network hourly (GHCNh) 1.1.0 (updated 2026-03-10)** (DOI 10.25921/jp3d-3v19).

Access: Bulk download of per-station per-year Apache Parquet files from the NOAA Open Data Dissemination (NODD) S3 bucket s3://noaa-ghcnh-pds (https://noaa-ghcnh-pds.s3.amazonaws.com), prefix hourly/access/by-year/{year}/parquet/GHCNh_{station_id}_{year}.parquet, fetched over HTTPS with urllib (read-only).

Access date: 2026-09-25.

## Why GHCNh and not ISD

The blueprint names NOAA ISD, but NCEI has superseded ISD with GHCNh: the GHCNh v1.1.0 documentation states it replaces the legacy Global Hourly (ISD) product, and NCEI ended ISD online service with no updates beyond 2025-08-24. GHCNh additionally reports station-level pressure and relative humidity natively. This switch is explicit, not silent.

## Stations

- `INI0000VIDD` SAFDARJUNG (North) 28.5845, 77.2058, median 180.0 min, 9,879 rows.
- `INI0000VIJP` JAIPUR (Northwest) 26.8242, 75.8122, median 30.0 min, 52,046 rows.
- `INI0000VILK` LUCKNOW (North-central) 26.7606, 80.8893, median 30.0 min, 48,669 rows.
- `INI0000VABB` CHHATRAPATI SHIVAJI INTL (West) 19.0887, 72.8679, median 30.0 min, 51,882 rows.
- `INI0000VABP` BHOPAL (Central) 23.2875, 77.3374, median 30.0 min, 28,405 rows.
- `INU042809-1` CALCUTTA/DUMDUM (East) 22.65, 88.45, median 30.0 min, 52,435 rows.
- `INU042410-1` GAUHATI (Northeast) 26.1, 91.58, median 30.0 min, 48,808 rows.
- `INI0000VOMM` CHENNAI INTL (Southeast) 12.9944, 80.1805, median 30.0 min, 52,022 rows.
- `INI0000VOBL` BANGALURU INTL AIRPORT (South) 13.2, 77.7, median 30.0 min, 52,289 rows.
- `INI0000VOTV` THIRUVANANTHAPURAM INTL (Far south) 8.4821, 76.9201, median 30.0 min, 51,710 rows.

Common overlap: 2022-01-01T00:00:00+00:00 → 2024-12-31T21:00:00+00:00 (26,302 hours).
Hourly temperature coverage: ≥2 stations 99.6%, ≥5 stations 99.4%, all stations 34.0% of common hours.

## Quality notes (audit, not faults)

- `INI0000VIDD`: 41 dewpoint>temperature rows; 1 candidate temperature discontinuities (>15C per step, for review).
- `INI0000VIJP`: 3 dewpoint>temperature rows.
- `INI0000VILK`: 1 dewpoint>temperature rows.
- `INI0000VABB`: 1 dewpoint>temperature rows.
- `INI0000VABP`: 4 dewpoint>temperature rows; 1 candidate temperature discontinuities (>15C per step, for review).
- `INU042809-1`: 1 dewpoint>temperature rows.
- `INU042410-1`: 19 dewpoint>temperature rows.
- `INI0000VOMM`: 2 dewpoint>temperature rows.
- `INI0000VOBL`: no integrity issues.
- `INI0000VOTV`: no integrity issues.

No meteorological extremes were deleted; all rows are preserved. No spatial score, neighbor claim, or capability claim is made here.

## Artifacts

- `data/noaa/processed/INI0000VIDD_2022_2024.csv` sha256 `3e634b91e1fd1d15…`
- `data/noaa/processed/INI0000VIJP_2022_2024.csv` sha256 `d05d7522cadacfb9…`
- `data/noaa/processed/INI0000VILK_2022_2024.csv` sha256 `d446b778e333598d…`
- `data/noaa/processed/INI0000VABB_2022_2024.csv` sha256 `999e8e8cb709a692…`
- `data/noaa/processed/INI0000VABP_2022_2024.csv` sha256 `aab707f561292a7e…`
- `data/noaa/processed/INU042809-1_2022_2024.csv` sha256 `59628283bc847dfe…`
- `data/noaa/processed/INU042410-1_2022_2024.csv` sha256 `07aa78c6656038cc…`
- `data/noaa/processed/INI0000VOMM_2022_2024.csv` sha256 `5a00616d0443294c…`
- `data/noaa/processed/INI0000VOBL_2022_2024.csv` sha256 `bda3fbd2f5c97266…`
- `data/noaa/processed/INI0000VOTV_2022_2024.csv` sha256 `9f8857996a2157c8…`

Manifest: `data/noaa/metadata/station_manifest.json`. Reproduce: `python -m src.noaa.run`.
