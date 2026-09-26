# Spatial Consistency Evidence Layer (Phase 8B)

Evidence signals only: per-variable spatial inconsistency versus nearby stations. NOT a fault classifier; signals are never combined here and no probability is claimed.

## Neighbor rule

Up to 3 nearest stations within 600.0 km (haversine), target excluded, deterministic rank by (distance, station ID). Fixed constants, tuned against nothing.

- `INI0000VIDD`: INI0000VIJP (239.02 km, coverage 100.0%); INI0000VILK (415.55 km, coverage 99.9%); INI0000VABP (589.15 km, coverage 98.9%).
- `INI0000VIJP`: INI0000VIDD (239.02 km, coverage 51.3%); INI0000VABP (422.19 km, coverage 78.0%); INI0000VILK (503.96 km, coverage 98.4%).
- `INI0000VILK`: INI0000VIDD (415.55 km, coverage 53.0%); INI0000VIJP (503.96 km, coverage 100.0%); INI0000VABP (526.45 km, coverage 80.4%).
- `INI0000VABB`: no neighbors within radius.
- `INI0000VABP`: INI0000VIJP (422.19 km, coverage 100.0%); INI0000VILK (526.45 km, coverage 99.9%); INI0000VIDD (589.15 km, coverage 58.6%).
- `INU042809-1`: INU042410-1 (497.61 km, coverage 98.2%).
- `INU042410-1`: INU042809-1 (497.61 km, coverage 100.0%).
- `INI0000VOMM`: INI0000VOBL (269.61 km, coverage 99.9%).
- `INI0000VOBL`: INI0000VOMM (269.61 km, coverage 99.9%); INI0000VOTV (531.47 km, coverage 99.3%).
- `INI0000VOTV`: INI0000VOBL (531.47 km, coverage 99.9%).

Temporal alignment: ±30 minutes (nearest real observation; no interpolation); UTC (Delhi AWS IST converted IST-5:30).

## Variables and pressure decision

Temperature (`temperature_c`) and relative humidity (`relative_humidity_pct`) scored separately. Pressure uses ONLY `altimeter_setting_hpa`: Altimeter (QNH, hPa) is the only pressure field with universal coverage; station-level and sea-level pressures are never mixed into it.

## Formulas

- Reference: neighbor_median = median of available neighbor observations (>= 1).
- Dispersion: MAD = median(|neighbor_i - median(neighbors)|), needs >= 2.
- Score: spatial_robust_score = |target - neighbor_median| / MAD; NaN when < 2 neighbors or MAD == 0; higher = stronger inconsistency, NOT a probability.
- Minimum neighbors: reference needs >= 1; score needs >= 2 with MAD > 0.
- Confidence: {'UNAVAILABLE': 'no target value or 0 available neighbors', 'LOW_CONTEXT': '1 available neighbor, or degenerate (MAD == 0) dispersion', 'MEDIUM_CONTEXT': '>= 2 available neighbors but fewer than expected', 'HIGH_CONTEXT': 'all expected neighbors available with a valid score'}.

## Coverage

- temp: 149,312.0/448,145 scored; HIGH 114,805.0, MEDIUM 34,507.0, LOW 244,972.0, UNAVAILABLE 53,861.0; abs-diff p50/p90/p99 3.0/7.0/10.0; score p50/p90/p99 2.333/10.0/25.0.
- rh: 153,945.0/448,145 scored; HIGH 116,405.0, MEDIUM 37,540.0, LOW 240,225.0, UNAVAILABLE 53,975.0; abs-diff p50/p90/p99 11.0/30.0/48.0; score p50/p90/p99 2.0/10.333/35.0.
- pres: 129,342.0/448,145 scored; HIGH 49,016.0, MEDIUM 80,326.0, LOW 248,704.0, UNAVAILABLE 70,099.0; abs-diff p50/p90/p99 3.0/6.5/8.0; score p50/p90/p99 2.5/9.0/13.0.
- alignment: FULL 334,306.0, PARTIAL 60,066.0, NONE 53,773.0.

Delhi AWS contextual coverage: 288,319/289,728 AWS rows (99.5%) have >= 1 NOAA context station; context = INI0000VIDD, INI0000VIJP, INI0000VILK, INI0000VABP (NOAA Delhi/Safdarjung plus its geographic neighbors; different sensors, not ground truth, no labels derived; AWS pressure never differenced against altimeter).

## Limitations

- Mumbai (`INI0000VABB`) has no station within 600 km (nearest, Bhopal, is ~655 km away), so all of its rows are UNAVAILABLE / NO_ALIGNMENT. The fixed radius was not adjusted to force a connection; the 8A station set was kept authoritative.
- Delhi/Safdarjung is 3-hourly: its own comparisons and AWS context are sparse in time.
- Altimeter (QNH) is a standard-atmosphere reduction, not a station-pressure comparison.
- High spatial difference is reported as inconsistency evidence, never as a sensor fault.
- Distances are geographic only; terrain and microclimate are not modeled.
