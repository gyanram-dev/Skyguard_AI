# NOAA Multi-Station Acquisition + Audit (Phase 8A)

Dataset: **Global Historical Climatology Network hourly (GHCNh) 1.1.0 (updated 2026-03-10)** (DOI 10.25921/jp3d-3v19).

Access: Bulk download of per-station per-year Apache Parquet files from the NOAA Open Data Dissemination (NODD) S3 bucket s3://noaa-ghcnh-pds (https://noaa-ghcnh-pds.s3.amazonaws.com), prefix hourly/access/by-year/{year}/parquet/GHCNh_{station_id}_{year}.parquet, fetched over HTTPS with urllib (read-only).

Access date: 2026-09-29.

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
- `INI0000VICG` CHANDIGARH (North) 30.6735, 76.7885, median 30.0 min, 2,764 rows.
- `INI0000VAPO` PUNE (West) 18.5821, 73.9197, median 30.0 min, 3,488 rows.
- `INI0000VOHS` HYDERABAD INTL AIRPORT (South-central) 17.2333, 78.4167, median 30.0 min, 49,747 rows.

Common overlap: 2022-08-17T08:30:00+00:00 → 2024-12-30T21:00:00+00:00 (20,798 hours).
Hourly temperature coverage: ≥2 stations 99.5%, ≥5 stations 99.3%, all stations 2.9% of common hours.

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
- `INI0000VICG`: 1 candidate temperature discontinuities (>15C per step, for review).
- `INI0000VAPO`: 4 candidate temperature discontinuities (>15C per step, for review).
- `INI0000VOHS`: no integrity issues.

No meteorological extremes were deleted; all rows are preserved. No spatial score, neighbor claim, or capability claim is made here.

## Artifacts

- `data/noaa/processed/INI0000VIDD_2022_2024.csv` sha256 `f893a811503fbd59…`
- `data/noaa/processed/INI0000VIJP_2022_2024.csv` sha256 `f02256df64398019…`
- `data/noaa/processed/INI0000VILK_2022_2024.csv` sha256 `ad7259226f038d0e…`
- `data/noaa/processed/INI0000VABB_2022_2024.csv` sha256 `dcdd1e401da492a3…`
- `data/noaa/processed/INI0000VABP_2022_2024.csv` sha256 `59184b9034ee679e…`
- `data/noaa/processed/INU042809-1_2022_2024.csv` sha256 `d6d094e3933d8dce…`
- `data/noaa/processed/INU042410-1_2022_2024.csv` sha256 `6d73587deeb14c12…`
- `data/noaa/processed/INI0000VOMM_2022_2024.csv` sha256 `b4ebade21a271d08…`
- `data/noaa/processed/INI0000VOBL_2022_2024.csv` sha256 `fe0425e277de6eb1…`
- `data/noaa/processed/INI0000VOTV_2022_2024.csv` sha256 `105478491eda1a56…`
- `data/noaa/processed/INI0000VICG_2022_2024.csv` sha256 `8c9759b79a0f3284…`
- `data/noaa/processed/INI0000VAPO_2022_2024.csv` sha256 `bc2a5373756d23e0…`
- `data/noaa/processed/INI0000VOHS_2022_2024.csv` sha256 `a124f6205aa76fc8…`

Manifest: `data/noaa/metadata/station_manifest.json`. Reproduce: `python -m src.noaa.run`.
