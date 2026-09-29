# Phase 24 Indian data audit

Source policy: (1) Delhi AWS bulk, (2) GHCNh bulk already in use (DOI 10.25921/jp3d-3v19, accessed 2026-09-25), (3) WIS2 capability entries (no bulk rows). No new downloads, no scraping, no substituted APIs.

## Capability findings (measured, not assumed)

- DELHI-AWS (Delhi-AWS): temp=True rh=True pres=True basis=station_level_hpa records=289728 cad=5.0 status=historical_bulk
- IMD-BENGALURU (IMD_WIS2): temp=True rh=False pres=True basis=station_level_hpa records=0 cad=180.0 status=live_capable
- IMD-DELHI (IMD_WIS2): temp=True rh=False pres=False basis=unavailable records=0 cad=180.0 status=live_capable
- IMD-KOLKATA (IMD_WIS2): temp=True rh=False pres=False basis=unavailable records=0 cad=180.0 status=live_capable
- IMD-PATNA (IMD_WIS2): temp=True rh=False pres=False basis=unavailable records=0 cad=180.0 status=live_capable
- IMD-PUNE (IMD_WIS2): temp=True rh=False pres=True basis=station_level_hpa records=0 cad=180.0 status=live_capable
- INI0000VABB (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=51882 cad=30.0 status=historical_bulk
- INI0000VABP (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=28405 cad=30.0 status=historical_bulk
- INI0000VIDD (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=9879 cad=180.0 status=historical_bulk
- INI0000VIJP (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=52046 cad=30.0 status=historical_bulk
- INI0000VILK (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=48669 cad=30.0 status=historical_bulk
- INI0000VOBL (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=52289 cad=30.0 status=historical_bulk
- INI0000VOMM (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=52022 cad=30.0 status=historical_bulk
- INI0000VOTV (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=51710 cad=30.0 status=historical_bulk
- INU042410-1 (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=48808 cad=30.0 status=historical_bulk
- INU042809-1 (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=52435 cad=30.0 status=historical_bulk
- JENA (Jena-benchmark): temp=True rh=True pres=True basis=station_level_hpa records=0 cad=10.0 status=benchmark_internal

## Excluded (with reasons)

- JENA / JENA-01: internal benchmark/regression dataset (Germany); never an Indian operational station
- AMD-06, HYD-07: mapping placeholders with no backend dataset; offline, excluded from operational counts
- Guwahati (beyond Gauhati GHCNh): no additional audited observations in the repository; Gauhati GHCNh (INU042410-1) is inventoried
- Chennai (beyond Chennai Intl GHCNh): covered by INI0000VOMM; no separate audited series in the repository

## Honesty notes

- RH is never manufactured from dew point (WIS2 stations report RH unavailable).
- Station pressure and MSL/altimeter are never mixed; Delhi-AWS pressure is station-level, GHCNh is altimeter.
- INI0000VIDD altimeter coverage is sparse (16%); its temperature/RH remain rich.
