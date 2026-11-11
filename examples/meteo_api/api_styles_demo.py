"""Одне й те саме спостереження станції 34504 через REST, GraphQL, WebSocket, SSE, webhook і gRPC.

    pip install -r requirements.txt
    python api_styles_demo.py
"""
import json
import logging
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from meteo_api.api_types import sign
from meteo_api.app import create_app
from meteo_api.grpc_meteo import connect, start_grpc_server
from meteo_api.storage import DATA_DIR, MeteoRepository

logging.getLogger("strawberry.execution").setLevel(logging.CRITICAL)   # помилку запиту показуємо самі
repo = MeteoRepository.from_files(DATA_DIR / "stations_sample.csv", DATA_DIR / "synop_sample.csv")
client = TestClient(create_app(repo))


def show(title: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    print(f"--- {title}\n{text}")


# REST: ресурс з адресою, сервер вирішує, які поля повернути
response = client.get("/api/v1/stations/34504/observations")
show(f"REST GET /api/v1/stations/34504/observations → {response.status_code}, {len(response.content)} байтів",
     response.json()["items"][-1])

# REST з ?fields= — вибір полів, але лише тих, що передбачив сервер
response = client.get("/api/v1/stations/34504/observations", params={"fields": "time,temperature"})
show(f"REST ?fields=time,temperature → {len(response.content)} байтів", response.json()["items"][-1])

# GraphQL: один POST /graphql, клієнт сам описує форму відповіді, включно з вкладеними даними
query = "{ station(wmo: \"34504\") { name observations(last: 1) { time temperature } } }"
response = client.post("/graphql", json={"query": query})
show(f"GraphQL POST /graphql → {response.status_code}, {len(response.content)} байтів", response.json())
response = client.post("/graphql", json={"query": "{ station(wmo: \"34504\") { altitude } }"})
show(f"GraphQL неіснуюче поле → {response.status_code}", response.json()["errors"][0]["message"])

# WebSocket: двосторонній канал; клієнт підписується, сервер шле сам
with client.websocket_connect("/ws/observations") as ws:
    ws.send_json({"subscribe": "34504"})
    messages = [ws.receive_json(), ws.receive_json()]
show("WebSocket /ws/observations", messages)
with client.websocket_connect("/ws/observations") as ws:
    ws.send_json({"subscribe": "00000"})
    error = ws.receive_json()
    try:
        ws.receive_json()
    except Exception as exc:                          # WebSocketDisconnect з кодом закриття
        show("WebSocket невідома станція", f"{error} → закрито з кодом {exc.code}")

# SSE: звичайний GET, відповідь — нескінченний text/event-stream
with client.stream("GET", "/events/observations", params={"station": "34504"}) as response:
    body = "".join(response.iter_text())
show(f"SSE GET /events/observations → {response.headers['content-type']}", body.strip())

# Webhook: сервер САМ робить POST на адресу клієнта, з підписом
received = []
receiver = FastAPI()


@receiver.post("/hook")
async def hook(request: Request) -> dict:
    body = await request.body()
    received.append((json.loads(body), request.headers["x-meteo-signature"] == sign(body)))
    return {"ok": True}


server = uvicorn.Server(uvicorn.Config(receiver, host="127.0.0.1", port=8033, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.05)
client.post("/webhooks", json={"url": "http://127.0.0.1:8033/hook"})
result = client.post("/webhooks/test-event", json={"station": "34504"}).json()
show(f"webhook → {result}", f"одержувач отримав {received[0][0]}, підпис вірний: {received[0][1]}")
server.should_exit = True

# gRPC: окремий сервер на HTTP/2, контракт — meteo.proto, тіло — бінарний protobuf
stub, pb2 = connect(start_grpc_server(repo, port=50052))
reply = stub.GetLatest(pb2.StationRequest(wmo="34504"))
show(f"gRPC GetLatest → {reply.ByteSize()} байтів protobuf", str(reply).strip().replace("\n", ", "))
try:
    stub.GetLatest(pb2.StationRequest(wmo="00000"))
except Exception as exc:
    show("gRPC невідома станція", f"{exc.code()} {exc.details()}")
