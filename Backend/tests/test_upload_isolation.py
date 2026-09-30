import pandas as pd
import pytest
import datetime
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from src.api.app import app
    with TestClient(app) as handle:
        yield handle

def create_multi_station_csv():
    start = datetime.datetime(2023, 1, 1, 0, 0, 0)
    data = []
    
    # Create 100 rows for BHOPAL
    for i in range(100):
        data.append({
            "ts": (start + datetime.timedelta(minutes=15*i)).isoformat(),
            "station": "BHOPAL",
            "temp": 30.0 + i*0.1,
            "rh": 50.0,
            "pres": 1010.0
        })
    data[50]["temp"] = 55.0
    
    # Create 150 rows for JAIPUR
    for i in range(150):
        data.append({
            "ts": (start + datetime.timedelta(minutes=15*i)).isoformat(),
            "station": "JAIPUR",
            "temp": 28.0 + i*0.05,
            "rh": 40.0,
            "pres": 1005.0
        })
        
    # Create 200 rows for PATNA
    for i in range(200):
        data.append({
            "ts": (start + datetime.timedelta(minutes=15*i)).isoformat(),
            "station": "PATNA",
            "temp": 25.0 + i*0.02,
            "rh": 60.0,
            "pres": 1012.0
        })

    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode("utf-8")

def create_single_station_csv():
    start = datetime.datetime(2023, 1, 1, 0, 0, 0)
    data = []
    for i in range(100):
        data.append({
            "ts": (start + datetime.timedelta(minutes=15*i)).isoformat(),
            "station": "BHOPAL",
            "temp": 30.0 + i*0.1,
            "rh": 50.0,
            "pres": 1010.0
        })
    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode("utf-8")

def test_multi_station_isolation(client: TestClient):
    csv_bytes = create_multi_station_csv()
    
    # Upload
    files = {"file": ("multi.csv", csv_bytes, "text/csv")}
    res = client.post("/api/v1/analyze/upload", files=files)
    assert res.status_code == 200
    session_id = res.json()["session_id"]
    detected = res.json()["stations_detected"]
    assert "BHOPAL" in detected
    assert "JAIPUR" in detected
    assert "PATNA" in detected
    
    # Confirm Mapping
    payload = {
        "mapping": {
            "timestamp": "ts",
            "temperature": "temp",
            "humidity": "rh",
            "pressure": "pres",
        },
        "units": {"temperature": "C", "pressure": "hPa"}
    }
    res = client.post(f"/api/v1/analyze/{session_id}/confirm", json=payload)
    assert res.status_code == 200
    preview = res.json()
    assert len(preview["stations"]) == 3
    
    # Run analysis for BHOPAL
    res = client.post(f"/api/v1/analyze/{session_id}/run?target_station=BHOPAL")
    assert res.status_code == 200
    res_bhopal = res.json()
    assert res_bhopal["observations"] == 100
    assert res_bhopal["station_label"] == "BHOPAL"
    assert res_bhopal["series"] is not None
    assert len(res_bhopal["series"]["timestamps"]) == 100
    
    # Run analysis for JAIPUR
    res = client.post(f"/api/v1/analyze/{session_id}/run?target_station=JAIPUR")
    assert res.status_code == 200
    res_jaipur = res.json()
    assert res_jaipur["observations"] == 150
    assert res_jaipur["station_label"] == "JAIPUR"
    assert res_jaipur["series"] is not None
    assert len(res_jaipur["series"]["timestamps"]) == 150
    
    # Run analysis for PATNA
    res = client.post(f"/api/v1/analyze/{session_id}/run?target_station=PATNA")
    assert res.status_code == 200
    res_patna = res.json()
    assert res_patna["observations"] == 200
    assert res_patna["station_label"] == "PATNA"
    assert res_patna["series"] is not None
    assert len(res_patna["series"]["timestamps"]) == 200

def test_single_station_workflow(client: TestClient):
    csv_bytes = create_single_station_csv()
    
    files = {"file": ("single.csv", csv_bytes, "text/csv")}
    res = client.post("/api/v1/analyze/upload", files=files)
    assert res.status_code == 200
    session_id = res.json()["session_id"]
    
    payload = {
        "mapping": {
            "timestamp": "ts",
            "temperature": "temp",
            "humidity": "rh",
            "pressure": "pres"
        },
        "units": {"temperature": "C", "pressure": "hPa"}
    }
    res = client.post(f"/api/v1/analyze/{session_id}/confirm", json=payload)
    assert res.status_code == 200
    
    res = client.post(f"/api/v1/analyze/{session_id}/run")
    assert res.status_code == 200
    res_single = res.json()
    assert res_single["observations"] == 100
    assert res_single["series"] is not None
    assert len(res_single["series"]["timestamps"]) == 100
