# Phase 22 spatial-decision evaluation

BASELINE = frozen `ens_median_flag`; SPATIAL-AWARE = same flags + contextual classification. The layer preserves flags by construction, so row/event detection metrics are expected to match; the measured contribution is interpretive (LOCAL vs REGIONAL vs UNCONFIRMED).

## Delhi test_in_distribution (n=57622)

- baseline: P=0.1356 R=0.0570 F1=0.0802 FPR=0.0239
- spatial-aware: P=0.1356 R=0.0570 F1=0.0802 FPR=0.0239
- flags identical: True
- events baseline: {'events': 120, 'events_detected': 62, 'event_recall': 0.5166666666666667, 'delay_median_min': 0.0}
- events spatial-aware: {'events': 120, 'events_detected': 62, 'event_recall': 0.5166666666666667, 'delay_median_min': 0.0}
- contextual on true positives: {'POSSIBLE_REGIONAL_EVENT': 80, 'ANOMALY_WITHOUT_SPATIAL_CONFIRMATION': 62, 'LOCAL_SENSOR_ANOMALY': 61}
- contextual on true negatives: {'NORMAL': 52765, 'POSSIBLE_REGIONAL_EVENT': 446, 'ANOMALY_WITHOUT_SPATIAL_CONFIRMATION': 434, 'LOCAL_SENSOR_ANOMALY': 414}
- temp spatial states: {'SPATIAL_SUPPORTED': 25192, 'SPATIAL_INSUFFICIENT': 18624, 'SPATIAL_CONTRADICTED': 13668, 'SPATIAL_UNAVAILABLE': 138}
- false alerts per station-day: 6.431478125808957

## Delhi test_generalization (n=56786)

- baseline: P=0.3120 R=0.1657 F1=0.2164 FPR=0.0350
- spatial-aware: P=0.3120 R=0.1657 F1=0.2164 FPR=0.0350
- flags identical: True
- events baseline: {'events': 140, 'events_detected': 94, 'event_recall': 0.6714285714285714, 'delay_median_min': 5.0}
- events spatial-aware: {'events': 140, 'events_detected': 94, 'event_recall': 0.6714285714285714, 'delay_median_min': 5.0}
- contextual on true positives: {'ANOMALY_WITHOUT_SPATIAL_CONFIRMATION': 381, 'LOCAL_SENSOR_ANOMALY': 355, 'POSSIBLE_REGIONAL_EVENT': 86}
- contextual on true negatives: {'NORMAL': 50012, 'ANOMALY_WITHOUT_SPATIAL_CONFIRMATION': 813, 'POSSIBLE_REGIONAL_EVENT': 708, 'LOCAL_SENSOR_ANOMALY': 292}
- temp spatial states: {'SPATIAL_SUPPORTED': 23666, 'SPATIAL_INSUFFICIENT': 23598, 'SPATIAL_CONTRADICTED': 8431, 'SPATIAL_UNAVAILABLE': 1091}
- false alerts per station-day: 9.011027698679783

## Paired scenarios (identical target, neighbors vary)

{'spike_local': 'LOCAL_SENSOR_ANOMALY', 'spike_regional': 'POSSIBLE_REGIONAL_EVENT', 'moderate_local': 'LOCAL_SENSOR_ANOMALY', 'moderate_regional': 'POSSIBLE_REGIONAL_EVENT'}
