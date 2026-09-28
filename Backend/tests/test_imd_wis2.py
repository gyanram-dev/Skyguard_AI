"""Phase 21A IMD WIS2 tests: parsing, normalization, bounds, failures.

All API responses are hand-built fixtures mirroring observed shapes;
no test touches the live IMD service.
"""

from __future__ import annotations

import pytest

from src.data_sources.imd_wis2 import client as C
from src.data_sources.imd_wis2 import normalizer as N
from src.data_sources.imd_wis2 import station_catalog as SC


def station_feature(trad="42492", name="PATNA", wigos="0-20000-0-42492",
                    status="operational", baro=57.0):
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [85.1, 25.6]},
            "properties": {
                "wigos_station_identifier": wigos,
                "traditional_station_identifier": trad,
                "name": name,
                "barometer_height": baro,
                "facility_type": "landFixed",
                "territory_name": "IND",
                "status": status,
                "topics": ["in-imd/data/core/weather/surface-based-observations/synop"]}}


def obs_feature(name, value, units="Celsius", ts="2026-08-02T12:00:00Z",
                wigos="0-20000-0-42492", report="0-20000-0-42492-202608021200"):
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [85.1, 25.6]},
            "id": f"{report}-0",
            "properties": {
                "name": name, "value": value, "units": units,
                "phenomenonTime": ts, "reportTime": ts,
                "reportId": report, "wigos_station_identifier": wigos,
                "id": f"{report}-0"}}


# 1. Station metadata parsing preserves official IDs.
def test_1_station_metadata():
    station = SC.parse_station(station_feature())
    assert station.wigos_id == "0-20000-0-42492"
    assert station.traditional_id == "42492"
    assert station.name == "PATNA"
    assert station.barometer_height == 57.0
    assert station.status == "operational"
    assert station.latitude == 25.6 and station.longitude == 85.1
    assert SC.find_by_traditional([station], "42492") is station
    assert SC.find_by_traditional([station], "99999") is None


# 2. Observation parsing keeps name/value/units/provenance.
def test_2_observation_parsing():
    record = N.parse_record(obs_feature("air_temperature", 31.4, "Celsius"))
    assert record.name == "air_temperature" and record.value == 31.4
    assert record.units == "Celsius"
    assert record.phenomenon_time == "2026-08-02T12:00:00Z"
    assert record.report_id == "0-20000-0-42492-202608021200"
    assert N.parse_record(obs_feature("air_temperature", None)).value is None


# 3. Temperature + pressure normalize; dewpoint ignored; MSL never used.
def test_3_variable_normalization():
    records = [N.parse_record(obs_feature("air_temperature", 31.4)),
               N.parse_record(obs_feature("dewpoint_temperature", 25.0)),
               N.parse_record(obs_feature("pressure_reduced_to_mean_sea_level",
                                          1000.0, "hPa")),
               N.parse_record(obs_feature("non_coordinate_pressure", 950.0, "hPa"))]
    obs = N.normalize_group("0-20000-0-42492", "PATNA", "2026-08-02T12:00:00Z",
                            records)
    assert obs.temperature_c == 31.4
    assert obs.relative_humidity_pct is None
    assert obs.pressure_hpa == 950.0
    assert obs.source == "IMD_WIS2"
    assert "air_temperature" in obs.source_variable_names
    assert "dewpoint_temperature" in obs.source_variable_names


# 4. Celsius passes through (verified units only).
def test_4_celsius():
    assert N.to_celsius(31.4, "Celsius", "air_temperature") == 31.4


# 5. hPa passes through; Pa converts; unknown units raise.
def test_5_hpa():
    assert N.to_hpa(950.0, "hPa", "non_coordinate_pressure") == 950.0
    assert N.to_hpa(95000.0, "Pa", "non_coordinate_pressure") == 950.0
    with pytest.raises(N.NormalizationError):
        N.to_hpa(950.0, "inHg", "non_coordinate_pressure")


# 6. UTC normalization keeps instants (Z, offset, naive).
def test_6_utc():
    assert N.parse_utc("2026-08-02T12:00:00Z").isoformat() == "2026-08-02T12:00:00+00:00"
    assert N.parse_utc("2026-08-02T12:00:00+00:00").isoformat() == \
        "2026-08-02T12:00:00+00:00"
    assert N.parse_utc("2026-08-02 12:00:00").isoformat() == "2026-08-02T12:00:00+00:00"


# 7. Missing RH stays missing (never derived).
def test_7_missing_rh():
    records = [N.parse_record(obs_feature("air_temperature", 31.4))]
    obs = N.normalize_group("0-20000-0-42492", "PATNA", "2026-08-02T12:00:00Z",
                            records)
    assert obs.relative_humidity_pct is None
    assert obs.temperature_c == 31.4


# 8. Missing station-level pressure stays missing despite MSL presence.
def test_8_missing_pressure():
    records = [N.parse_record(obs_feature("air_temperature", 31.4)),
               N.parse_record(obs_feature("pressure_reduced_to_mean_sea_level",
                                          1000.0, "hPa"))]
    obs = N.normalize_group("0-20000-0-42492", "PATNA", "2026-08-02T12:00:00Z",
                            records)
    assert obs.pressure_hpa is None


# 9. Station-level vs MSL pressure are never mixed.
def test_9_pressure_distinction():
    only_msl = [N.parse_record(obs_feature("pressure_reduced_to_mean_sea_level",
                                           1000.0, "hPa"))]
    assert N.normalize_group("w", "S", "t", only_msl).pressure_hpa is None
    both = only_msl + [N.parse_record(obs_feature("non_coordinate_pressure",
                                                  950.0, "hPa"))]
    assert N.normalize_group("w", "S", "t", both).pressure_hpa == 950.0


# 10. Pagination stops at the bound and rejects bad pages.
def test_10_pagination():
    pages = [{"features": [{"a": 1}, {"b": 2}]}, {"features": []}]

    class FakeClient(C.IMDWIS2Client):
        def __init__(self):
            super().__init__(base_url="http://x", ca_bundle=None)

        def get_observations(self, wigos_id, limit=1000, offset=0):
            assert 1 <= limit <= 1000 and offset >= 0
            return pages[0] if offset == 0 else pages[1]

    seen = [page for page in FakeClient().iter_observations("0-20000-0-42492",
                                                            max_records=3000)]
    assert seen == [[{"a": 1}, {"b": 2}]]
    with pytest.raises(C.IMDWIS2Error):
        list(FakeClient().iter_observations("0-20000-0-42492", max_records=0))
    with pytest.raises(C.IMDWIS2Error):
        FakeClient._check_page(5000, 0)


# 11+12. Malformed responses and transport failures stay structured.
def test_11_12_malformed_and_transport():
    with pytest.raises(ValueError):
        SC.parse_catalogue({"nope": True})
    with pytest.raises(KeyError):
        SC.parse_station({"properties": {"name": "X"}})
    with pytest.raises(C.IMDWIS2Error):
        C.IMDWIS2Client(base_url="http://127.0.0.1:9",
                        ca_bundle=None, timeout_s=1).get_stations(limit=1)


# 13. Provenance answers where every value came from.
def test_13_provenance():
    records = [N.parse_record(obs_feature("air_temperature", 31.4)),
               N.parse_record(obs_feature("non_coordinate_pressure", 950.0,
                                          "hPa"))]
    obs = N.normalize_group("0-20000-0-42492", "PATNA", "2026-08-02T12:00:00Z",
                            records, latitude=25.6, longitude=85.1, elevation=57.0)
    assert obs.source_station_id == "0-20000-0-42492"
    assert obs.provenance["temperature"]["variable"] == "air_temperature"
    assert obs.provenance["temperature"]["units"] == "Celsius"
    assert obs.provenance["pressure"]["variable"] == "non_coordinate_pressure"
    assert obs.latitude == 25.6 and obs.elevation == 57.0


# 14. Station filtering rejects blank IDs without network use.
def test_14_station_filtering():
    with pytest.raises(C.IMDWIS2Error):
        C.IMDWIS2Client(base_url="http://x").get_observations("   ")
