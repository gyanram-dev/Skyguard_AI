"""Phase 24 report builder: inventory, network, validation, summaries.

Reads audited repository data only. Writes (Backend mirror; the caller
mirrors to root ``reports/phase24/``):
- reports/phase24/indian_station_inventory.json
- reports/phase24/indian_data_audit.md
- reports/phase24/indian_network.json
- reports/phase24/indian_validation_report.md
- reports/phase24/phase24_summary.md
"""

from __future__ import annotations

import json
from pathlib import Path

from src.indian_network import inventory as INV
from src.indian_network import network as NET


def main(root: str | Path = ".") -> dict:
    root = Path(root)
    out = root / "reports" / "phase24"
    out.mkdir(parents=True, exist_ok=True)
    inventory = INV.build_inventory(root)
    registry = NET.build_registry(inventory)
    (out / "indian_station_inventory.json").write_text(
        json.dumps({"version": INV.INVENTORY_VERSION,
                    "stations": inventory}, indent=2), encoding="utf-8")
    (out / "indian_network.json").write_text(
        json.dumps(registry, indent=2), encoding="utf-8")
    stats = _aggregate(inventory, registry)
    (out / "indian_data_audit.md").write_text(
        _audit_md(inventory, stats), encoding="utf-8")
    (out / "indian_validation_report.md").write_text(
        _validation_md(inventory, registry, stats), encoding="utf-8")
    (out / "phase24_summary.md").write_text(
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
    ("AMD-06, HYD-07", "mapping placeholders with no backend dataset; "
     "offline, excluded from operational counts"),
    ("Guwahati (beyond Gauhati GHCNh)", "no additional audited observations "
     "in the repository; Gauhati GHCNh (INU042410-1) is inventoried"),
    ("Chennai (beyond Chennai Intl GHCNh)", "covered by INI0000VOMM; "
     "no separate audited series in the repository"),
)


def _audit_md(inventory: list, stats: dict) -> str:
    lines = ["# Phase 24 Indian data audit", "",
             "Source policy: (1) Delhi AWS bulk, (2) GHCNh bulk already in "
             "use (DOI 10.25921/jp3d-3v19, accessed 2026-09-25), "
             "(3) WIS2 capability entries (no bulk rows). No new downloads, "
             "no scraping, no substituted APIs.", "",
             "## Capability findings (measured, not assumed)", ""]
    for e in inventory:
        lines.append(
            f"- {e['station_id']} ({e['source']}): temp="
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
    lines = ["# Indian validation bundle (Phase 24)", "",
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
              "A. Real Indian observations: Delhi AWS + 10 GHCNh stations + "
              "WIS2 live capability (5 audited stations).",
              "B. Controlled/synthetic: PATNA/JAIPUR/BHOPAL-TEST-01 fixtures "
              "(tests + controlled live only).",
              "C. Jena internal benchmark: regression only, absent from this "
              "registry and all Indian counts."]
    return "\n".join(lines) + "\n"


def _summary_md(stats: dict) -> str:
    return "\n".join([
        "# Phase 24 summary", "",
        f"- inventory entries: {stats['inventory_entries']}",
        f"- registry stations: {stats['registry_stations']} "
        f"({stats['operational']} operational)",
        f"- bulk observations: {stats['total_bulk_observations']:,}",
        f"- temp-compatible spatial edges: {stats['temp_compatible_edges']}",
        "- Jena: benchmark_internal, excluded from registry and counts",
        "- thresholds/models/Phase-22 policy: unchanged",
        "- next recommended phase: freeze/drift redesign (explicitly "
        "deferred by phase scope)",
        ""]) + "\n"


if __name__ == "__main__":
    print(main("."))
