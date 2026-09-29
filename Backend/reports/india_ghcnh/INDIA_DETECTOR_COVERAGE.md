# INDIA detector coverage (measured)

City | Station | T | P | RH | Joint coverage | Detector | Status

| Mumbai | INI0000VABB | yes | altimeter only | yes (reported) | T/RH ~100%, slp ~0% | statistical (validated, uncalibrated) | PARTIAL |
| Hyderabad | INI0000VOHS | yes | altimeter only | yes (reported) | T/RH ~100%, slp 0% | statistical path only | PARTIAL |
| Chennai | INI0000VOMM | yes | altimeter only | yes (reported) | T/RH ~100%, slp 16% | statistical path only | PARTIAL |
| Bengaluru | INI0000VOBL | yes | altimeter only | yes (reported) | T/RH ~100%, slp 0% | statistical path only | PARTIAL |
| Pune | INI0000VAPO | yes | altimeter only | yes (reported) | sparse rows (69 ext.) | statistical path only | PARTIAL |
| Kolkata | INU042809-1 | yes | altimeter only | yes (reported) | T/RH ~100%, slp ~0% | statistical path only | PARTIAL |
| Bhopal | INI0000VABP | yes | altimeter only | yes (reported) | T/RH ~100%, slp 31% | statistical path only | PARTIAL |
| Jaipur | INI0000VIJP | yes | altimeter only | yes (reported) | T/RH ~100%, slp ~0% | statistical path only | PARTIAL |
| Lucknow | INI0000VILK | yes | altimeter only | yes (reported) | T/RH ~100%, slp 2% | statistical path only | PARTIAL |
| Chandigarh | INI0000VICG | yes | altimeter only | yes (reported) | sparse rows (2435 ext.) | statistical path only | PARTIAL |
| Delhi | DELHI-AWS | yes | station-level | yes | full | statistical+IF+LSTM+RC (frozen) | FULL_TPR (existing) |

"Detector" here means validated statistical-baseline response on real
station data (Mumbai measured; peers share the pipeline path). No city
is FULL_TPR: station-level pressure is absent and Delhi calibration
does not transfer. IF/LSTM/RC remain Delhi-only. OOD evaluation of new
models and replay wiring are deferred future work, stated openly.

Spatial context: Mumbai spike vs compatible neighbors discriminates
(CONTRADICTED, score 32.2) while normal reads agree (SUPPORTED, 0.25)
using the unchanged Phase-22 layer; sub-600km peers are sparse for
Mumbai (Pune 124 km, often missing) so INSUFFICIENT/UNAVAILABLE is the
honest common outcome.
