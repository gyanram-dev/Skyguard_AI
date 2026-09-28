"""Official IMD WIS2 observation adapter (Phase 21A: ingestion boundary).

Reads station metadata and SYNOP observation records from the official
IMD wis2box OGC API. No fabrication, no unit guessing, no dew-point to
humidity conversion, no station/MSL pressure mixing. Network failures
surface as structured errors; nothing here touches the frontend.
"""
