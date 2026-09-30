"""Direct WS replay test: start DEL-01 at max speed, count streamed readings."""
import asyncio
import json
import sys
import urllib.request

sys.path.insert(0, ".")


async def main() -> None:
    import websockets

    async with websockets.connect("ws://127.0.0.1:8000/api/v1/live") as ws:
        conn = json.loads(await ws.recv())
        print("connection:", conn["type"], conn["source_mode"])
        await ws.send(json.dumps({"action": "start", "station_id": "DEL-01",
                                  "split": "OOD", "speed": 3600}))
        readings, anomalies, states, errors = 0, 0, 0, []
        last_state = None
        try:
            while readings < 40:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
                mtype = msg.get("type")
                if mtype == "reading":
                    readings += 1
                elif mtype == "alert":
                    anomalies += 1
                elif mtype == "replay_state":
                    states += 1
                    last_state = msg.get("status")
                elif mtype == "error":
                    errors.append(msg.get("code"))
                    break
                elif mtype == "complete":
                    break
        except asyncio.TimeoutError:
            print("TIMEOUT waiting for messages")
        print(f"readings={readings} alerts={anomalies} states={states} "
              f"last_state={last_state} errors={errors}")


urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health").read()
asyncio.run(main())
