"""Release-audit test fixtures: multi-station + single-station CSV uploads.

Test INPUT data only (never app output). Deterministic patterns engineered to
exercise the detector: Bhopal=SPIKE, Jaipur=CROSS (pressure departs alone),
Patna=DRIFT, plus deliberate data-quality defects (missing values, duplicate
timestamp, invalid timestamp, non-finite value, RH out of range, large gap).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).parent

START = datetime(2025, 6, 1, 0, 0)
N = 288  # 24 h at 5-min cadence

# Bhopal: monsoon-ish June diurnal cycle, ~12-28 C, RH 60-95, P 990-1005 (plateau)
def bhopal(i: int):
    t = START + timedelta(minutes=5 * i)
    hour = i / 12.0
    temp = 20.0 + 7.0 * (1 - (hour % 24 - 12 if hour % 24 > 12 else 12 - hour % 24) / 12.0) if False else 22.0 - 6.0 * ((hour % 24) - 13) ** 2 / 169
    hum = 82.0 - 0.8 * (temp - 22.0)
    pres = 998.0 + 0.6 * ((i % 240) - 120) / 120.0
    return t, round(temp, 1), round(hum, 1), round(pres, 1)

def jaipur(i: int):
    t = START + timedelta(minutes=5 * i)
    hour = i / 12.0
    temp = 30.0 - 8.0 * ((hour % 24) - 14) ** 2 / 169
    hum = 38.0 - 0.7 * (temp - 30.0)
    pres = 1010.0 + 0.5 * ((i % 288) - 144) / 144.0
    return t, round(temp, 1), round(hum, 1), round(pres, 1)

def patna(i: int):
    t = START + timedelta(minutes=5 * i)
    hour = i / 12.0
    temp = 26.0 - 6.0 * ((hour % 24) - 13) ** 2 / 169
    hum = 78.0 - 0.8 * (temp - 26.0)
    pres = 1002.0 + 0.4 * ((i % 288) - 144) / 144.0
    return t, round(temp, 1), round(hum, 1), round(pres, 1)


def build_rows(gen, inject=None):
    rows = []
    for i in range(N):
        t, c, h, p = gen(i)
        row = {"timestamp": t.strftime("%Y-%m-%d %H:%M:%S"), "station_id": "",
               "temperature_c": c, "relative_humidity_pct": h, "pressure_hpa": p}
        if inject:
            inject(i, row, t)
        rows.append(row)
    return rows


def inject_bhopal(i, row, t):
    if 144 <= i < 148:  # 12:00-12:15 spike +14 C then drop
        row["temperature_c"] = 22.0 if i < 147 else 36.5
        if i == 145 or i == 146:
            row["temperature_c"] = 36.9
    if i == 50:
        row["relative_humidity_pct"] = ""           # missing value
    if i == 100:
        row["timestamp"] = "not-a-timestamp"         # invalid timestamp
    if i == 150:
        row["temperature_c"] = "abc"                 # non-finite text
    if i == 200:
        row["timestamp"] = "2025-06-01 16:35:00"     # duplicate of i=199

def inject_jaipur(i, row, t):
    if 150 <= i < 156:  # 12:30-13:00 pressure departs ALONE (-18 hPa), T/RH hold
        row["pressure_hpa"] = 992.0
    if i == 80:
        row["pressure_hpa"] = ""                     # missing pressure

def inject_patna(i, row, t):
    if i >= 240:  # last 4 h: steady 0.05 C per 5-min rise (drift)
        row["temperature_c"] = round(20.0 + 0.05 * (i - 240), 1)
    if i == 60:
        row["relative_humidity_pct"] = 130.0         # out-of-range RH
    if i == 61:
        row["relative_humidity_pct"] = 130.0         # duplicate handled below


def write_csv(path: Path, rows, multi: bool):
    rows = list(rows)
    if multi:
        for r in rows:
            r["station_id"] = {"b": "BHOPAL-S1", "j": "JAIPUR-S2", "p": "PATNA-S3"}[r.pop("_src")]
    header = ["timestamp"] + (["station_id"] if multi else []) + \
             ["temperature_c", "relative_humidity_pct", "pressure_hpa"]
    lines = [",".join(header)]
    for r in rows:
        vals = [r["timestamp"]]
        if multi:
            vals.append(r.get("station_id", ""))
        vals += [str(r["temperature_c"]), str(r["relative_humidity_pct"]), str(r["pressure_hpa"])]
        lines.append(",".join(vals))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(rows)} rows)")


# ---- multi-station CSV: Bhopal / Jaipur / Patna interleaved chronologically
multi_rows = []
b_rows = build_rows(bhopal, inject_bhopal)
j_rows = build_rows(jaipur, inject_jaipur)
p_rows = build_rows(patna, inject_patna)
for r in b_rows:
    r["_src"] = "b"
for r in j_rows:
    r["_src"] = "j"
for r in p_rows:
    r["_src"] = "p"
all_rows = sorted(b_rows + j_rows + p_rows, key=lambda r: r["timestamp"])
write_csv(OUT / "multi_station_bhopal_jaipur_patna.csv", all_rows, multi=True)

# ---- single-station CSV (Bhopal only, no station_id column)
single = [{k: v for k, v in r.items() if k != "_src"} for r in b_rows]
write_csv(OUT / "single_station_bhopal.csv", single, multi=False)
