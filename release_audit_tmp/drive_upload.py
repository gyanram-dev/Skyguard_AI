"""Drive the analyze/upload pipeline end-to-end (audit script, test input only)."""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1/analyze"


def multipart_upload(path: str) -> dict:
    boundary = "----auditaudit"
    body = (f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{path.split('/')[-1]}\"\r\n"
            f"Content-Type: text/csv\r\n\r\n").encode() + \
        open(path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/upload", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req).read())


def post_json(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req).read())


def get_json(path: str) -> dict:
    return json.loads(urllib.request.urlopen(BASE + path).read())


def analyze(path: str, multi: bool):
    up = multipart_upload(path)
    print(f"\n== {path}: rows={up['rows']} stations_detected={up['stations_detected']}")
    payload = {"mapping": {"timestamp": "timestamp", "temperature": "temperature_c",
                           "humidity": "relative_humidity_pct", "pressure": "pressure_hpa"},
               "units": {"temperature": "C", "pressure": "hPa"}}
    dq = post_json(f"/{up['session_id']}/confirm", payload)
    print(f"dq: rows={dq['rows']} cadence={dq['cadence_min']}ml_eligible={dq['ml_eligible']} "
          f"dups={dq['duplicates']} invalid_ts={dq['invalid_timestamps']} "
          f"non_finite={dq['non_finite']} rh_invalid={dq.get('rh_invalid')} gaps={dq['large_gaps']}")
    print(f"missing={dq['missing']} stations={[(s.get('station'), s.get('rows')) for s in dq['stations']]}")

    stations = [s.get("station") for s in dq["stations"]]
    for st in stations:
        res = post_json(f"/{up['session_id']}/run?target_station={urllib.request.quote(st)}", {})
        anomalies = res["anomalies_detail"]
        types = {}
        for a in anomalies:
            types[a["root_cause_estimate"]] = types.get(a["root_cause_estimate"], 0) + 1
        stamps = sorted({a["timestamp"] for a in anomalies})
        cross = {a["station"] for a in anomalies} - {st}
        ev0 = anomalies[0]["evidence"] if anomalies else {}
        print(f"[{st}] obs={res['observations']} anomalies={res['anomalies']} "
              f"dq_events={res['dq_events']} types={types} series={res.get('series') is not None}")
        print(f"    anomaly range: {stamps[0] if stamps else '-'} .. {stamps[-1] if stamps else '-'}")
        print(f"    CROSS-STATION LEAK: {cross if cross else 'NONE'}")
        if anomalies:
            a0 = anomalies[0]
            print(f"    first: {a0['timestamp']} score={a0['score']} expl={a0['explanation'][:110]}")
            print(f"    ml_models={ev0.get('ml_models')} spatial={ {k:v for k,v in ev0.get('spatial',{}).items() if k!='spatial_decision'} }")
    return stations


if __name__ == "__main__":
    import os
    HERE = os.path.dirname(os.path.abspath(__file__))
    analyze(os.path.join(HERE, "multi_station_bhopal_jaipur_patna.csv"), True)
    analyze(os.path.join(HERE, "single_station_bhopal.csv"), False)
    print("\nDONE")
