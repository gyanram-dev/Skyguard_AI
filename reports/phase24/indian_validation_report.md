# Indian validation bundle (Phase 24)

- registry stations: 16 (8 operational, 3 with data but unmapped, 5 live-capable)
- with temperature/RH/pressure: 16/11/13
- bulk observations: 737,873
- bulk coverage: ['2022-01-01 00:00:00+00:00', '2024-12-31 23:55:00']
- median cadence: 30.0 min
- duplicates/out-of-order/gaps: 0/0/5364
- missing temp/RH/pres: 881/968/13831
- temperature-compatible neighbor edges: 41

## Per-station inference capabilities

- DELHI-AWS [operational] vars=pressure,relative_humidity,temperature records=289728 cad=5.0 neighbors=3
- IMD-BENGALURU [live_capable] vars=pressure,temperature records=0 cad=180.0 neighbors=3
- IMD-DELHI [live_capable] vars=temperature records=0 cad=180.0 neighbors=3
- IMD-KOLKATA [live_capable] vars=temperature records=0 cad=180.0 neighbors=3
- IMD-PATNA [live_capable] vars=temperature records=0 cad=180.0 neighbors=3
- IMD-PUNE [live_capable] vars=pressure,temperature records=0 cad=180.0 neighbors=1
- INI0000VABB [operational] vars=pressure,relative_humidity,temperature records=51882 cad=30.0 neighbors=1
- INI0000VABP [operational] vars=pressure,relative_humidity,temperature records=28405 cad=30.0 neighbors=3
- INI0000VIDD [data_available_unmapped] vars=pressure,relative_humidity,temperature records=9879 cad=180.0 neighbors=3
- INI0000VIJP [operational] vars=pressure,relative_humidity,temperature records=52046 cad=30.0 neighbors=3
- INI0000VILK [operational] vars=pressure,relative_humidity,temperature records=48669 cad=30.0 neighbors=3
- INI0000VOBL [operational] vars=pressure,relative_humidity,temperature records=52289 cad=30.0 neighbors=3
- INI0000VOMM [operational] vars=pressure,relative_humidity,temperature records=52022 cad=30.0 neighbors=2
- INI0000VOTV [data_available_unmapped] vars=pressure,relative_humidity,temperature records=51710 cad=30.0 neighbors=2
- INU042410-1 [data_available_unmapped] vars=pressure,relative_humidity,temperature records=48808 cad=30.0 neighbors=2
- INU042809-1 [operational] vars=pressure,relative_humidity,temperature records=52435 cad=30.0 neighbors=3

## Scope separation

A. Real Indian observations: Delhi AWS + 10 GHCNh stations + WIS2 live capability (5 audited stations).
B. Controlled/synthetic: PATNA/JAIPUR/BHOPAL-TEST-01 fixtures (tests + controlled live only).
C. Jena internal benchmark: regression only, absent from this registry and all Indian counts.
