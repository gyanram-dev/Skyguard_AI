import pandas as pd
from src.api.app import app
from fastapi.testclient import TestClient



def create_csv(single=False):
    import datetime
    
    start = datetime.datetime(2023, 1, 1, 0, 0, 0)
    data = []
    
    # Create 100 rows for BHOPAL
    for i in range(100):
        data.append({
            "ts": (start + datetime.timedelta(minutes=15*i)).isoformat(),
            "station": "BHOPAL-01",
            "temp": 30.0 + i*0.1,
            "rh": 50.0,
            "pres": 1010.0
        })
    data[50]["temp"] = 55.0
    
    if not single:
        # Create 150 rows for JAIPUR
        for i in range(150):
            data.append({
                "ts": (start + datetime.timedelta(minutes=15*i)).isoformat(),
                "station": "JAIPUR-01",
                "temp": 28.0 + i*0.05,
                "rh": 40.0,
                "pres": 1005.0
            })
            
        # Create 200 rows for PATNA
        for i in range(200):
            data.append({
                "ts": (start + datetime.timedelta(minutes=15*i)).isoformat(),
                "station": "PATNA-01",
                "temp": 25.0 + i*0.02,
                "rh": 60.0,
                "pres": 1012.0
            })

    df = pd.DataFrame(data)
    return df.to_csv(index=False)

def test_workflow():
    csv_data = create_csv()
    csv_data_single = create_csv(single=True)
    
    with TestClient(app) as client:
        # 1. Upload
        print("Uploading Multi-Station CSV...")
    files = {"file": ("test.csv", csv_data, "text/csv")}
    res = client.post("/api/v1/analyze/upload", files=files)
    res.raise_for_status()
    session = res.json()
    session_id = session["session_id"]
    print("Detected stations:", session["stations_detected"])
    assert "BHOPAL-01" in session["stations_detected"]
    assert "JAIPUR-01" in session["stations_detected"]
    
    # 2. Confirm Mapping
    print("Confirming mapping...")
    payload = {
        "mapping": {
            "timestamp": "ts",
            "temperature": "temp",
            "humidity": "rh",
            "pressure": "pres"
        },
        "units": {
            "temperature": "C",
            "pressure": "hPa"
        }
    }
    res = client.post(f"/api/v1/analyze/{session_id}/confirm", json=payload)
    res.raise_for_status()
    preview = res.json()
    print("Preview multiple stations:", len(preview["stations"]))
    assert len(preview["stations"]) == 3
    
    # 3. Analyze BHOPAL-01
    print("\nRunning analysis on BHOPAL-01...")
    res = client.post(f"/api/v1/analyze/{session_id}/run?target_station=BHOPAL-01")
    res.raise_for_status()
    result = res.json()
    
    print("BHOPAL-01 Results:")
    print("- Observations:", result["observations"])
    print("- Station Label:", result["station_label"])
    print("- Series Length:", len(result["series"]["timestamps"]) if result.get("series") else "None")
    assert result["observations"] == 100
    assert result["station_label"] == "BHOPAL-01"
    assert result["series"] is not None
    assert len(result["series"]["timestamps"]) == 100
    
    # 4. Analyze JAIPUR-01
    print("\nRunning analysis on JAIPUR-01...")
    res = client.post(f"/api/v1/analyze/{session_id}/run?target_station=JAIPUR-01")
    res.raise_for_status()
    result = res.json()
    print("JAIPUR-01 Results:")
    print("- Observations:", result["observations"])
    print("- Station Label:", result["station_label"])
    assert result["observations"] == 150
    assert result["station_label"] == "JAIPUR-01"

    # 5. Analyze Single Station
    csv_data_single = create_csv(single=True)
    files = {"file": ("single.csv", csv_data_single, "text/csv")}
    res = client.post("/api/v1/analyze/upload", files=files)
    session_id = res.json()["session_id"]
    res = client.post(f"/api/v1/analyze/{session_id}/confirm", json=payload)
    # run without target_station
    res = client.post(f"/api/v1/analyze/{session_id}/run")
    result = res.json()
    print("\nSingle Station Results:")
    print("- Observations:", result["observations"])
    print("- Station Label:", result["station_label"])
    assert result["observations"] == 100
    assert result["series"] is not None
    
    print("\nALL VERIFICATIONS PASSED")

if __name__ == "__main__":
    test_workflow()
