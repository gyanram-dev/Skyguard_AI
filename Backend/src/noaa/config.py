"""Phase 8A configuration: source identity, station shortlist, mapping.

Dataset choice (documented, not silent): GHCNh v1.1.0 instead of ISD.
- The blueprint names NOAA ISD, but NCEI has superseded ISD with GHCNh:
  the GHCNh v1.1.0 documentation (2026-03-10) states GHCNh "replaces the
  legacy Global Hourly product, also known as ISD", and NCEI announced the
  end of ISD online service with no ISD updates beyond 2025-08-24
  (NESDIS notice 2026-06-23), directing users to GHCNh.
- GHCNh additionally provides station_level_pressure and relative_humidity
  natively, which ISD station files report only sparsely or not at all.
ISD was evaluated as the fallback and rejected for the reasons above.
"""

from __future__ import annotations

DATASET_NAME = "Global Historical Climatology Network hourly (GHCNh)"
DATASET_VERSION = "1.1.0 (updated 2026-03-10)"
DATASET_DOI = "10.25921/jp3d-3v19"
DATASET_PAGES = [
    "https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly",
    "https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc:C01688/html",
]
ACCESS_METHOD = (
    "Bulk download of per-station per-year Apache Parquet files from the "
    "NOAA Open Data Dissemination (NODD) S3 bucket s3://noaa-ghcnh-pds "
    "(https://noaa-ghcnh-pds.s3.amazonaws.com), prefix "
    "hourly/access/by-year/{year}/parquet/GHCNh_{station_id}_{year}.parquet, "
    "fetched over HTTPS with urllib (read-only)."
)
INVENTORY_SOURCE = (
    "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/"
    "hourly/doc/ghcnh-station-list.txt (38,870 stations; snapshot stored "
    "under data/noaa/metadata/)."
)
DOC_PDF = (
    "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/"
    "hourly/doc/ghcnh_DOCUMENTATION.pdf"
)
# A snapshot of DOC_PDF is stored under data/noaa/metadata/ for provenance.

# Acquisition window: aligns with the Delhi-NCR AWS validation period
# (2022-04-01 → 2024-12-31) so the spatial layer can later be evaluated
# against the same Indian weather the rest of SkyGuard was validated on.
YEARS = (2022, 2023, 2024)

# Shortlist: 13 Indian stations, geographically distributed (north,
# northwest, north-central, west, central, east, northeast, southeast,
# south, far south). Coordinates/elevations are copied verbatim from the
# GHCNh station-list inventory (see metadata snapshot). Selection
# prioritized full 2022-2024 file availability plus temperature, pressure,
# and humidity coverage; fame of the city was not a criterion.
STATIONS: tuple[dict, ...] = (
    {"ghcnh_id": "INI0000VIDD", "name": "SAFDARJUNG", "region": "North",
     "lat": 28.5845, "lon": 77.2058, "elev_m": 214.9,
     "note": "Delhi; closest GHCNh station to the Delhi-NCR AWS data."},
    {"ghcnh_id": "INI0000VIJP", "name": "JAIPUR", "region": "Northwest",
     "lat": 26.8242, "lon": 75.8122, "elev_m": 385.0, "note": ""},
    {"ghcnh_id": "INI0000VILK", "name": "LUCKNOW", "region": "North-central",
     "lat": 26.7606, "lon": 80.8893, "elev_m": 125.0, "note": ""},
    {"ghcnh_id": "INI0000VABB", "name": "CHHATRAPATI SHIVAJI INTL", "region": "West",
     "lat": 19.0887, "lon": 72.8679, "elev_m": 11.3, "note": "Mumbai."},
    {"ghcnh_id": "INI0000VABP", "name": "BHOPAL", "region": "Central",
     "lat": 23.2875, "lon": 77.3374, "elev_m": 524.0, "note": ""},
    {"ghcnh_id": "INU042809-1", "name": "CALCUTTA/DUMDUM", "region": "East",
     "lat": 22.65, "lon": 88.45, "elev_m": 6.0, "note": "Kolkata airport."},
    {"ghcnh_id": "INU042410-1", "name": "GAUHATI", "region": "Northeast",
     "lat": 26.10, "lon": 91.58, "elev_m": 54.0, "note": "Guwahati."},
    {"ghcnh_id": "INI0000VOMM", "name": "CHENNAI INTL", "region": "Southeast",
     "lat": 12.9944, "lon": 80.1805, "elev_m": 15.8, "note": ""},
    {"ghcnh_id": "INI0000VOBL", "name": "BANGALURU INTL AIRPORT", "region": "South",
     "lat": 13.20, "lon": 77.70, "elev_m": 915.0, "note": "Bengaluru."},
    {"ghcnh_id": "INI0000VOTV", "name": "THIRUVANANTHAPURAM INTL", "region": "Far south",
     "lat": 8.4821, "lon": 76.9201, "elev_m": 4.6, "note": ""},
    {"ghcnh_id": "INI0000VICG", "name": "CHANDIGARH", "region": "North",
     "lat": 30.6735, "lon": 76.7885, "elev_m": 308.5, "note": ""},
    {"ghcnh_id": "INI0000VAPO", "name": "PUNE", "region": "West",
     "lat": 18.5821, "lon": 73.9197, "elev_m": 591.9, "note": ""},
    {"ghcnh_id": "INI0000VOHS", "name": "HYDERABAD INTL AIRPORT", "region": "South-central",
     "lat": 17.2333, "lon": 78.4167, "elev_m": 617.0, "note": ""},
)

# SkyGuard concept -> GHCNh source field. Units per GHCNh documentation:
# temperature/dewpoint in degrees Celsius, pressures in hPa, RH in percent.
# station_level_pressure is the true barometric pressure at station
# elevation; sea_level_pressure is a reduced estimate, NOT station
# pressure; altimeter is reduced to mean sea level with the standard
# atmosphere (millibars/hPa). None are substituted for each other.
VARIABLE_MAPPING: tuple[dict, ...] = (
    {"skyguard": "temperature_c", "source_field": "temperature",
     "unit": "degC", "role": "primary",
     "note": "Dry-bulb air temperature."},
    {"skyguard": "station_level_pressure_hpa", "source_field": "station_level_pressure",
     "unit": "hPa", "role": "primary",
     "note": "True barometric pressure at station elevation. Sparse at "
             "METAR-fed stations; absent values stay missing, never filled."},
    {"skyguard": "sea_level_pressure_hpa", "source_field": "sea_level_pressure",
     "unit": "hPa", "role": "primary",
     "note": "Reduction estimate to sea level using the station temperature "
             "profile. Documented as-is; NOT station pressure."},
    {"skyguard": "altimeter_setting_hpa", "source_field": "altimeter",
     "unit": "hPa", "role": "auxiliary",
     "note": "QNH reduced with the standard atmosphere. Universally reported; "
             "candidate common pressure basis for Phase 8B, undecided here."},
    {"skyguard": "relative_humidity_pct", "source_field": "relative_humidity",
     "unit": "percent", "role": "primary",
     "note": "Natively reported; no derivation needed."},
    {"skyguard": "dew_point_temperature_c", "source_field": "dew_point_temperature",
     "unit": "degC", "role": "humidity-equivalent",
     "note": "Defensible humidity-equivalent backup where RH is missing; no "
             "RH is manufactured from it in this phase."},
)

# Provider missing-value sentinel (per GHCNh documentation); mapped to NaN.
MISSING_SENTINEL = -9999

# Earth-physical plausibility envelopes used ONLY to flag integrity
# problems for audit reporting. Suspicious in-envelope values are kept.
PHYSICAL_BOUNDS = {
    "temperature_c": (-89.2, 56.7),       # WMO world records
    "station_level_pressure_hpa": (870.0, 1085.0),
    "sea_level_pressure_hpa": (870.0, 1085.0),
    "altimeter_setting_hpa": (870.0, 1085.0),
    "relative_humidity_pct": (0.0, 100.0),  # strict: >100% is non-physical
}
