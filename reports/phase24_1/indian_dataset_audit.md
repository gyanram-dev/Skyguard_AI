# Phase 24.1 Indian data audit

Source policy: (1) Delhi AWS bulk, (2) GHCNh bulk already in use (DOI 10.25921/jp3d-3v19, accessed 2026-09-25), (3) official IMD WIS2 capability entries (no bulk rows). Only the three newly selected public GHCNh station-year sets were acquired; no scraping or substituted APIs.

## Capability findings (measured, not assumed)

- DELHI-AWS [REAL_HISTORICAL] (Delhi-AWS): temp=True rh=True pres=True basis=station_level_hpa records=289728 cad=5.0 status=historical_bulk
- IMD-BENGALURU [LIVE_CAPABLE] (IMD_WIS2): temp=True rh=False pres=True basis=station_level_hpa records=0 cad=180.0 status=live_capable
- IMD-DELHI [LIVE_CAPABLE] (IMD_WIS2): temp=True rh=False pres=False basis=unavailable records=0 cad=180.0 status=live_capable
- IMD-KOLKATA [LIVE_CAPABLE] (IMD_WIS2): temp=True rh=False pres=False basis=unavailable records=0 cad=180.0 status=live_capable
- IMD-PATNA [LIVE_CAPABLE] (IMD_WIS2): temp=True rh=False pres=False basis=unavailable records=0 cad=180.0 status=live_capable
- IMD-PUNE [LIVE_CAPABLE] (IMD_WIS2): temp=True rh=False pres=True basis=station_level_hpa records=0 cad=180.0 status=live_capable
- INI0000VABB [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=51882 cad=30.0 status=historical_bulk
- INI0000VABP [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=28405 cad=30.0 status=historical_bulk
- INI0000VAPO [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=3488 cad=30.0 status=historical_bulk
- INI0000VICG [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=2764 cad=30.0 status=historical_bulk
- INI0000VIDD [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=9879 cad=180.0 status=historical_bulk
- INI0000VIJP [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=52046 cad=30.0 status=historical_bulk
- INI0000VILK [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=48669 cad=30.0 status=historical_bulk
- INI0000VOBL [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=52289 cad=30.0 status=historical_bulk
- INI0000VOHS [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=49747 cad=30.0 status=historical_bulk
- INI0000VOMM [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=52022 cad=30.0 status=historical_bulk
- INI0000VOTV [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=51710 cad=30.0 status=historical_bulk
- INU042410-1 [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=48808 cad=30.0 status=historical_bulk
- INU042809-1 [REAL_HISTORICAL] (GHCNh): temp=True rh=True pres=True basis=altimeter_qnh_hpa records=52435 cad=30.0 status=historical_bulk

## Excluded (with reasons)

- JENA / JENA-01: internal benchmark/regression dataset (Germany); never an Indian operational station
- Ahmedabad: no station with an audited 2022-2024 historical series was identified in the local GHCNh inventory
- Nagpur (INU00042867): station-list record exists, but the 2022-2024 station-year objects were unavailable
- Guwahati (beyond Gauhati GHCNh): no additional audited observations in the repository; Gauhati GHCNh (INU042410-1) is inventoried
- Chennai (beyond Chennai Intl GHCNh): covered by INI0000VOMM; no separate audited series in the repository

## Honesty notes

- RH is never manufactured from dew point (WIS2 stations report RH unavailable).
- Station pressure and MSL/altimeter are never mixed; Delhi-AWS pressure is station-level, GHCNh is altimeter.
- INI0000VIDD altimeter coverage is sparse (16%); its temperature/RH remain rich.
