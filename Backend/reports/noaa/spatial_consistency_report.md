# Spatial Consistency Evidence Layer (Phase 8B)

Evidence signals only: per-variable spatial inconsistency versus nearby stations. NOT a fault classifier; signals are never combined here and no probability is claimed.

## Neighbor rule

Up to 3 nearest stations within 600.0 km (haversine), target excluded, deterministic rank by (distance, station ID). Fixed constants, tuned against nothing.

- `INI0000VIDD`: INI0000VIJP (239.02 km, coverage 99.9%); INI0000VILK (415.55 km, coverage 99.8%); INI0000VABP (589.15 km, coverage 98.3%).
- `INI0000VIJP`: INI0000VIDD (239.02 km, coverage 35.2%); INI0000VABP (422.19 km, coverage 69.0%); INI0000VILK (503.96 km, coverage 97.4%).
- `INI0000VILK`: INI0000VIDD (415.55 km, coverage 36.6%); INI0000VIJP (503.96 km, coverage 99.9%); INI0000VABP (526.45 km, coverage 71.6%).
- `INI0000VABB`: no neighbors within radius.
- `INI0000VABP`: INI0000VIJP (422.19 km, coverage 99.9%); INI0000VILK (526.45 km, coverage 99.7%); INI0000VIDD (589.15 km, coverage 46.4%).
- `INU042809-1`: INU042410-1 (497.61 km, coverage 96.2%).
- `INU042410-1`: INU042809-1 (497.61 km, coverage 100.0%).
- `INI0000VOMM`: INI0000VOBL (269.61 km, coverage 99.9%).
- `INI0000VOBL`: INI0000VOMM (269.61 km, coverage 99.8%); INI0000VOTV (531.47 km, coverage 99.1%).
- `INI0000VOTV`: INI0000VOBL (531.47 km, coverage 99.9%).

Temporal alignment: 30 minutes back from target (latest real observation at/before target; future records never selected; no interpolation); UTC (Delhi AWS IST converted IST-5:30).

## Variables and pressure decision

Temperature (`temperature_c`) and relative humidity (`relative_humidity_pct`) scored separately. Pressure uses ONLY `altimeter_setting_hpa`: Altimeter (QNH, hPa) is the only pressure field with universal coverage; station-level and sea-level pressures are never mixed into it.

## Formulas

- Reference: neighbor_median = median of available neighbor observations (>= 1).
- Dispersion: MAD = median(|neighbor_i - median(neighbors)|), needs >= 2.
- Score: spatial_robust_score = |target - neighbor_median| / MAD; NaN when < 2 neighbors or MAD == 0; higher = stronger inconsistency, NOT a probability.
- Minimum neighbors: reference needs >= 1; score needs >= 2 with MAD > 0.
- Confidence: {'UNAVAILABLE': 'no target value or 0 available neighbors', 'LOW_CONTEXT': '1 available neighbor, or degenerate (MAD == 0) dispersion', 'MEDIUM_CONTEXT': '>= 2 available neighbors but fewer than expected', 'HIGH_CONTEXT': 'all expected neighbors available with a valid score'}.

## Coverage

- temp: 141,562.0/448,145 scored; HIGH 97,709.0, MEDIUM 43,853.0, LOW 251,125.0, UNAVAILABLE 55,458.0; abs-diff p50/p90/p99 3.0/7.0/10.0; score p50/p90/p99 2.333/9.5/24.0.
- rh: 146,103.0/448,145 scored; HIGH 98,399.0, MEDIUM 47,704.0, LOW 246,471.0, UNAVAILABLE 55,571.0; abs-diff p50/p90/p99 11.0/30.0/48.0; score p50/p90/p99 2.0/10.0/36.0.
- pres: 123,580.0/448,145 scored; HIGH 48,619.0, MEDIUM 74,961.0, LOW 253,447.0, UNAVAILABLE 71,118.0; abs-diff p50/p90/p99 3.0/6.5/8.0; score p50/p90/p99 2.5/9.0/13.0.
- alignment: FULL 313,205.0, PARTIAL 79,570.0, NONE 55,370.0.

Delhi AWS contextual coverage: 286,777/289,728 AWS rows (99.0%) have >= 1 NOAA context station; context = INI0000VIDD, INI0000VIJP, INI0000VILK, INI0000VABP (NOAA Delhi/Safdarjung plus its geographic neighbors; different sensors, not ground truth, no labels derived; AWS pressure never differenced against altimeter).

## Limitations

- Mumbai (`INI0000VABB`) has no station within 600 km (nearest, Bhopal, is ~655 km away), so all of its rows are UNAVAILABLE / NO_ALIGNMENT. The fixed radius was not adjusted to force a connection; the 8A station set was kept authoritative.
- Delhi/Safdarjung is 3-hourly: its own comparisons and AWS context are sparse in time.
- Altimeter (QNH) is a standard-atmosphere reduction, not a station-pressure comparison.
- High spatial difference is reported as inconsistency evidence, never as a sensor fault.
- Distances are geographic only; terrain and microclimate are not modeled.
