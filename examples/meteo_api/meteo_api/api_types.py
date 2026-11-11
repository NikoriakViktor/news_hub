"""Ті самі метеодані через різні типи API (урок 32, розділ «Які бувають API»).

Кожна функція install_* додає до FastAPI-застосунку один стиль API:

    /cgi-bin/getsynop   HTTP-API у стилі ogimet: GET з параметрами → CSV
    /rpc                JSON-RPC 2.0: один URL, назва методу в тілі
    /graphql            GraphQL: клієнт сам обирає поля
    /soap               SOAP: XML-конверт
    /ws/observations    WebSocket: двосторонній канал, сервер шле сам
    /events/observations  Server-Sent Events: односторонній потік подій
    /webhooks           Webhook: сервер сам робить POST на адресу клієнта

gRPC працює поверх HTTP/2 окремим сервером — див. grpc_meteo.py.
"""
import asyncio
import hashlib
import hmac
import json
import xml.etree.ElementTree as ET
from typing import List, Optional

import httpx
import strawberry
from fastapi import Body, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from strawberry.fastapi import GraphQLRouter

from .storage import NotFoundError, format_time, parse_time

WEBHOOK_SECRET = b"meteo-webhook-secret"      # навчальний; справжній — зі змінної середовища


def sign(body: bytes) -> str:
    """Підпис тіла webhook: HMAC-SHA256 (урок 16) — одержувач перевіряє, що лист від нас."""
    return hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- HTTP + CSV (як ogimet)
def install_csv(app, repo):
    @app.get("/cgi-bin/getsynop", response_class=PlainTextResponse)
    def getsynop(block: str, begin: str, end: str):
        """Двійник ogimet getsynop: begin/end — YYYYMMDDHHmm, відповідь — CSV без заголовка."""
        start, finish = (parse_time(f"{v[:4]}-{v[4:6]}-{v[6:8]}T{v[8:10]}:{v[10:12]}Z") for v in (begin, end))
        try:
            items = repo.list_observations(block, start, finish)
        except NotFoundError:
            items = []
        return "".join(
            f"{o['station']},{o['time']:%Y,%m,%d,%H,%M},{o['telegram']}\n" for o in items
        )


# ---------------------------------------------------------------- JSON-RPC 2.0
def install_rpc(app, repo):
    def latest_temperature(wmo):
        items = repo.list_observations(wmo)
        if not items:
            raise NotFoundError(f"немає спостережень станції {wmo}")
        return {"time": format_time(items[-1]["time"]), "temperature": items[-1]["temperature"]}

    methods = {
        "station.get": lambda wmo: repo.get_station(wmo),
        "temperature.latest": latest_temperature,
        "stations.count": lambda: len(repo.list_stations()),
    }

    @app.post("/rpc")
    def rpc(call: dict = Body(...)):
        call_id = call.get("id")
        method = methods.get(call.get("method"))
        if method is None:
            error = {"code": -32601, "message": f"метод {call.get('method')!r} не існує"}
            return {"jsonrpc": "2.0", "error": error, "id": call_id}
        try:
            result = method(**call.get("params", {}))
        except NotFoundError as e:
            return {"jsonrpc": "2.0", "error": {"code": 404, "message": str(e)}, "id": call_id}
        except TypeError as e:
            return {"jsonrpc": "2.0", "error": {"code": -32602, "message": str(e)}, "id": call_id}
        return {"jsonrpc": "2.0", "result": result, "id": call_id}


# ---------------------------------------------------------------- GraphQL
def install_graphql(app, repo):
    @strawberry.type
    class Observation:
        time: str
        temperature: Optional[float]
        pressure: Optional[float]
        wind_speed: Optional[float]

    def to_observation(obs):
        return Observation(time=format_time(obs["time"]), temperature=obs.get("temperature"),
                           pressure=obs.get("pressure"), wind_speed=obs.get("wind_speed"))

    @strawberry.type
    class Station:
        wmo: str
        name: str
        lat: Optional[float]
        lon: Optional[float]

        @strawberry.field
        def observations(self, last: int = 3) -> List[Observation]:
            return [to_observation(o) for o in repo.list_observations(self.wmo)[-last:]]

    def to_station(s):
        return Station(wmo=s["wmo"], name=s["name"], lat=s["lat"], lon=s["lon"])

    @strawberry.type
    class Query:
        @strawberry.field
        def station(self, wmo: str) -> Optional[Station]:
            try:
                return to_station(repo.get_station(wmo))
            except NotFoundError:
                return None

        @strawberry.field
        def stations(self) -> List[Station]:
            return [to_station(s) for s in repo.list_stations()]

    app.include_router(GraphQLRouter(strawberry.Schema(query=Query)), prefix="/graphql")


# ---------------------------------------------------------------- SOAP
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
METEO_NS = "urn:meteo"


def soap_envelope(body_xml):
    return (f'<?xml version="1.0" encoding="utf-8"?>\n'
            f'<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:m="{METEO_NS}">'
            f'<soap:Body>{body_xml}</soap:Body></soap:Envelope>')


def install_soap(app, repo):
    @app.post("/soap")
    async def soap(request: Request):
        try:
            root = ET.fromstring(await request.body())
            call = root.find(f"{{{SOAP_NS}}}Body/{{{METEO_NS}}}GetLatestTemperature")
            wmo = call.findtext(f"{{{METEO_NS}}}Station")
            items = repo.list_observations(wmo)
            last = items[-1]
            body = (f"<m:GetLatestTemperatureResponse><m:Station>{wmo}</m:Station>"
                    f"<m:Time>{format_time(last['time'])}</m:Time>"
                    f"<m:Temperature>{last['temperature']}</m:Temperature></m:GetLatestTemperatureResponse>")
            return Response(soap_envelope(body), media_type="text/xml; charset=utf-8")
        except (ET.ParseError, AttributeError, IndexError, NotFoundError) as e:
            fault = (f"<soap:Fault><faultcode>soap:Client</faultcode>"
                     f"<faultstring>{type(e).__name__}: {e}</faultstring></soap:Fault>")
            return Response(soap_envelope(fault), status_code=500, media_type="text/xml; charset=utf-8")


# ---------------------------------------------------------------- WebSocket і SSE
def install_streams(app, repo):
    @app.websocket("/ws/observations")
    async def ws_observations(websocket: WebSocket):
        """Клієнт надсилає {"subscribe": "34504"} — сервер шле спостереження по одному."""
        await websocket.accept()
        try:
            request = await websocket.receive_json()
            for obs in repo.list_observations(request["subscribe"]):
                await websocket.send_json({"time": format_time(obs["time"]), "temperature": obs["temperature"]})
                await asyncio.sleep(0.05)            # «нове спостереження надійшло»
            await websocket.send_json({"done": True})
            await websocket.close()
        except (NotFoundError, KeyError) as e:
            await websocket.send_json({"error": str(e)})
            await websocket.close(code=1008)
        except WebSocketDisconnect:
            pass

    @app.get("/events/observations")
    def sse_observations(station: str = Query(...)):
        """Server-Sent Events: text/event-stream, подія на кожне спостереження."""
        items = repo.list_observations(station)

        async def events():
            for obs in items:
                data = json.dumps({"time": format_time(obs["time"]), "temperature": obs["temperature"]})
                yield f"event: observation\ndata: {data}\n\n"
                await asyncio.sleep(0.05)
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")


# ---------------------------------------------------------------- Webhook
def install_webhooks(app, repo):
    subscribers = []

    @app.post("/webhooks", status_code=201)
    def subscribe(url: str = Body(..., embed=True)):
        """Клієнт реєструє свою адресу: «коли буде нове спостереження — надішли POST сюди»."""
        subscribers.append(url)
        return {"url": url, "events": ["observation.created"]}

    @app.post("/webhooks/test-event", status_code=202)
    async def fire_test_event(station: str = Body(..., embed=True)):
        """Імітує нове спостереження: сервер САМ робить POST кожному підписнику."""
        obs = repo.list_observations(station)[-1]
        body = json.dumps({"event": "observation.created", "station": station,
                           "time": format_time(obs["time"]), "temperature": obs["temperature"]},
                          ensure_ascii=False).encode()
        delivered = 0
        async with httpx.AsyncClient(timeout=5) as client:
            for url in subscribers:
                response = await client.post(url, content=body, headers={
                    "Content-Type": "application/json", "X-Meteo-Signature": sign(body)})
                delivered += response.is_success
        return {"delivered": delivered, "subscribers": len(subscribers)}


def install(app, repo):
    install_csv(app, repo)
    install_rpc(app, repo)
    install_graphql(app, repo)
    install_soap(app, repo)
    install_streams(app, repo)
    install_webhooks(app, repo)
