"""Phase 24 report builder: inventory, network, validation, summaries.

Reads audited repository data only. Writes the Phase 24.1 bundle to the
repository-level ``reports/phase24_1/`` directory:
- reports/phase24_1/indian_dataset_inventory.json
- reports/phase24_1/indian_dataset_audit.md
- reports/phase24_1/indian_station_capabilities.csv
- reports/phase24_1/indian_network.json
- reports/phase24_1/live_provider_setup.md
- reports/phase24_1/phase24_1_summary.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.indian_network import inventory as INV
from src.indian_network import network as NET


def main(root: str | Path = ".") -> dict:
    root = Path(root).resolve()
    out = root.parent / "reports" / "phase24_1"
    out.mkdir(parents=True, exist_ok=True)
    full_inventory = INV.build_inventory(root)
    inventory = [entry for entry in full_inventory
                 if entry["classification"] in ("REAL_HISTORICAL", "LIVE_CAPABLE")]
    benchmark_internal = [entry for entry in full_inventory
                          if entry["classification"] == "BENCHMARK_INTERNAL"]
    registry = NET.build_registry(full_inventory)
    (out / "indian_dataset_inventory.json").write_text(
        json.dumps({"version": "phase24.1",
                    "scope": "Indian operational network",
                    "stations": inventory,
                    "scope_counts": {
                        "REAL_HISTORICAL": sum(e["classification"] == "REAL_HISTORICAL"
                                                for e in inventory),
                        "LIVE_CAPABLE": sum(e["classification"] == "LIVE_CAPABLE"
                                             for e in inventory),
                        "CONTROLLED": 0,
                        "BENCHMARK_INTERNAL": len(benchmark_internal)},
                    "benchmark_internal": benchmark_internal},
                   indent=2), encoding="utf-8")
    (out / "indian_network.json").write_text(
        json.dumps(registry, indent=2), encoding="utf-8")
    stats = _aggregate(inventory, registry)
    (out / "indian_dataset_audit.md").write_text(
        _audit_md(inventory, stats), encoding="utf-8")
    capability_columns = (
        "station_id", "station_name", "classification", "source",
        "source_station_id", "latitude", "longitude", "elevation_m",
        "coverage_start", "coverage_end", "record_count", "cadence_min",
        "temperature_available", "relative_humidity_available",
        "pressure_available", "pressure_basis", "missingness",
        "duplicate_count", "out_of_order_count", "gap_count", "provenance")
    rows = [{**entry,
             "missingness": json.dumps(entry.get("missingness"), sort_keys=True),
             "provenance": json.dumps(entry.get("provenance"), sort_keys=True)}
            for entry in inventory]
    pd.DataFrame(rows, columns=capability_columns).to_csv(
        out / "indian_station_capabilities.csv", index=False)
    (out / "live_provider_setup.md").write_text(
        _live_setup_md(), encoding="utf-8")
    (out / "phase24_1_summary.md").write_text(
        _summary_md(stats), encoding="utf-8")
    return stats


def _aggregate(inventory: list, registry: dict) -> dict:
    bulk = [e for e in inventory if e["source_status"] == "historical_bulk"]
    live = [e for e in inventory if e["source_status"] == "live_capable"]
    stations = registry["stations"]
    compat_edges = sum(1 for s in stations for n in s["spatial_neighbors"]
                       if n["temperature_compatible"])
    return {
        "inventory_entries": len(inventory),
        "registry_stations": len(stations),
        "operational": sum(1 for s in stations
                           if s["operational_status"] == "operational"),
        "unmapped_with_data": sum(1 for s in stations
                                  if s["operational_status"]
                                  == "data_available_unmapped"),
        "live_capable": sum(1 for s in stations
                            if s["operational_status"] == "live_capable"),
        "with_temperature": sum(1 for s in stations
                                if "temperature" in s["available_variables"]),
        "with_rh": sum(1 for s in stations
                       if "relative_humidity" in s["available_variables"]),
        "with_pressure": sum(1 for s in stations
                             if "pressure" in s["available_variables"]),
        "total_bulk_observations": sum(e["record_count"] for e in bulk),
        "bulk_coverage": [min(e["coverage_start"] for e in bulk if
                              e["coverage_start"]),
                          max(e["coverage_end"] for e in bulk if
                              e["coverage_end"])],
        "median_cadence_min": sorted(e["cadence_min"] for e in bulk
                                     if e["cadence_min"])[len(bulk) // 2],
        "total_duplicates": sum(e["duplicate_count"] for e in bulk),
        "total_out_of_order": sum(e["out_of_order_count"] for e in bulk),
        "total_gaps": sum(e["gap_count"] for e in bulk),
        "missing_temp": sum(e["missing_temperature"] for e in bulk),
        "missing_rh": sum(e["missing_relative_humidity"] for e in bulk),
        "missing_pres": sum(e["missing_pressure"] for e in bulk),
        "temp_compatible_edges": compat_edges,
        "live_capability_stations": [e["station_id"] for e in live],
    }


EXCLUDED = (
    ("JENA / JENA-01", "internal benchmark/regression dataset (Germany); "
     "never an Indian operational station"),
    ("Ahmedabad", "no station with an audited 2022-2024 historical series "
     "was identified in the local GHCNh inventory"),
    ("Nagpur (INU00042867)", "station-list record exists, but the 2022-2024 "
     "station-year objects were unavailable"),
    ("Guwahati (beyond Gauhati GHCNh)", "no additional audited observations "
     "in the repository; Gauhati GHCNh (INU042410-1) is inventoried"),
    ("Chennai (beyond Chennai Intl GHCNh)", "covered by INI0000VOMM; "
     "no separate audited series in the repository"),
)


def _audit_md(inventory: list, stats: dict) -> str:
    lines = ["# Phase 24.1 Indian data audit", "",
             "Source policy: (1) Delhi AWS bulk, (2) GHCNh bulk already in "
             "use (DOI 10.25921/jp3d-3v19, accessed 2026-09-25), "
             "(3) official IMD WIS2 capability entries (no bulk rows). "
             "Only the three newly selected public GHCNh station-year sets "
             "were acquired; no scraping or substituted APIs.", "",
             "## Capability findings (measured, not assumed)", ""]
    for e in inventory:
        lines.append(
            f"- {e['station_id']} [{e['classification']}] ({e['source']}): temp="
            f"{e['temperature_available']} rh={e['relative_humidity_available']} "
            f"pres={e['pressure_available']} basis={e['pressure_basis']} "
            f"records={e['record_count']} cad={e['cadence_min']} "
            f"status={e['source_status']}")
    lines += ["", "## Excluded (with reasons)", ""]
    for name, reason in EXCLUDED:
        lines.append(f"- {name}: {reason}")
    lines += ["", "## Honesty notes", "",
              "- RH is never manufactured from dew point (WIS2 stations "
              "report RH unavailable).",
              "- Station pressure and MSL/altimeter are never mixed; "
              "Delhi-AWS pressure is station-level, GHCNh is altimeter.",
              "- INI0000VIDD altimeter coverage is sparse (16%); its "
              "temperature/RH remain rich."]
    return "\n".join(lines) + "\n"


def _validation_md(inventory: list, registry: dict, stats: dict) -> str:
    lines = ["# Indian validation bundle (Phase 24.1)", "",
             f"- registry stations: {stats['registry_stations']} "
             f"({stats['operational']} operational, "
             f"{stats['unmapped_with_data']} with data but unmapped, "
             f"{stats['live_capable']} live-capable)",
             f"- with temperature/RH/pressure: {stats['with_temperature']}/"
             f"{stats['with_rh']}/{stats['with_pressure']}",
             f"- bulk observations: {stats['total_bulk_observations']:,}",
             f"- bulk coverage: {stats['bulk_coverage']}",
             f"- median cadence: {stats['median_cadence_min']} min",
             f"- duplicates/out-of-order/gaps: {stats['total_duplicates']}/"
             f"{stats['total_out_of_order']}/{stats['total_gaps']}",
             f"- missing temp/RH/pres: {stats['missing_temp']}/"
             f"{stats['missing_rh']}/{stats['missing_pres']}",
             f"- temperature-compatible neighbor edges: "
             f"{stats['temp_compatible_edges']}",
             "",
             "## Per-station inference capabilities", ""]
    for s in registry["stations"]:
        cov = s["data_coverage"]
        lines.append(
            f"- {s['station_id']} [{s['operational_status']}] "
            f"vars={','.join(s['available_variables'])} "
            f"records={cov['records']} cad={cov['cadence_min']} "
            f"neighbors={len(s['spatial_neighbors'])}")
    lines += ["", "## Scope separation", "",
              "A. REAL_HISTORICAL: Delhi AWS + 13 GHCNh stations.",
              "B. LIVE_CAPABLE: five WIS2 stations with audited field capability; "
              "no bulk observations are claimed.",
              "C. CONTROLLED: only scripted tests/demo; not part of the Indian "
              "station inventory or counts.",
              "D. BENCHMARK_INTERNAL: Jena regression artifacts only, excluded "
              "from this registry and all Indian counts."]
    return "\n".join(lines) + "\n"


def _summary_md(stats: dict) -> str:
    return "\n".join([
          "# Phase 24.1 summary", "",
        f"- inventory entries: {stats['inventory_entries']}",
          f"- Indian network stations: {stats['registry_stations']} "
          f"({stats['operational']} historical, {stats['live_capable']} live-capable)",
        f"- bulk observations: {stats['total_bulk_observations']:,}",
          f"- bulk coverage: {stats['bulk_coverage']}",
        f"- temp-compatible spatial edges: {stats['temp_compatible_edges']}",
          "- Jena: BENCHMARK_INTERNAL, excluded from operational registry and Indian counts",
        "- thresholds/models/Phase-22 policy: unchanged",
          "- Phase 25: not started; wait for the Phase 24.1 acceptance review.",
        ""]) + "\n"


def _live_setup_md() -> str:
     return """# Live provider setup (Phase 24.1)

The configured adapter is the official IMD WIS2 OGC API at
`https://wis2box.imd.gov.in/oapi`. Its published collection API does not
document API-key, bearer-token, or client-secret authentication; this setup
therefore does not invent credential variables. Configure the provider URL
and, only when required by deployment trust, a PEM CA bundle. TLS verification
is always enabled.

1. Copy `Backend/.env.example` to a deployment-managed `.env` file outside Git.
2. Set `LIVE_SOURCE_MODE=LIVE_IMD`, `LIVE_PROVIDER=IMD_WIS2`, and
    `IMD_BASE_URL` to the authorized endpoint. Set `IMD_CA_BUNDLE` only when a
    provider-issued CA chain is needed.
3. If a protected provider documents header authentication, set
   `IMD_REQUEST_HEADERS` to a JSON object of its required headers, such as an
   `Authorization` or API-key header. For documented mutual TLS, set
   `IMD_CLIENT_CERT` and `IMD_CLIENT_KEY`. These values are optional, are not
   required by public WIS2, and must come from the provider's contract.
4. Start the backend with `python -m src.api.run` from `Backend/`; the entry
   point loads `.env` (or `SKYGUARD_ENV_FILE`) before app initialization.
5. Start ingestion from the Live page or `POST /api/v1/live/start`.
6. The adapter contacts the WIS2 station-observation collection. An empty
    result is still a successful connection; credentials alone never imply
    `CONNECTED`.
7. The adapter normalizes WIS2 fields to canonical observations. The existing
    data-quality, causal history, inference, spatial context, alert episode,
    and SQLite persistence flow then runs without provider fields downstream.
8. Check `/api/v1/live/status`: `NOT_CONFIGURED` means required endpoint
   configuration is absent; `CONFIGURED` means the endpoint is set but no
   successful heartbeat has completed; `CONNECTION_FAILED` means a configured
   request failed; `CONNECTED` is reported only after a successful provider
   response.

If IMD later supplies a protected endpoint, follow its published auth contract.
No secret is currently required by the public WIS2 OGC API. Provider auth
headers and client-certificate paths are never included in logs, structured
errors, or API status. `IMD_ARG` remains a separate contract-only adapter
until IMD publishes an authorized endpoint/schema.
"""


if __name__ == "__main__":
    print(main("."))
