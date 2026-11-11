"""Meteo API v2 — REST-версія метео-API викладача (урок 32).

Було (legacy/main.py): /download_telegrams, POST /filter_telegrams/, /telegram/{collection}/{id}.
Стало: ресурси «станції» і «спостереження», методи HTTP за призначенням, чесні статус-коди.

    uvicorn meteo_api.app:app --port 8032          # Swagger: http://127.0.0.1:8032/docs

або з Python / Jupyter:

    from meteo_api.app import start_server
    BASE = start_server()                          # http://127.0.0.1:8032, сервер у фоновому потоці
"""
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .storage import ConflictError, MeteoRepository, NotFoundError, format_time, parse_ogimet_csv, parse_time

OBSERVATION_FIELDS = ["station", "time", "temperature", "dew_point", "relative_humidity", "wind_dir",
                      "wind_speed", "pressure", "sea_level_pressure", "max_temperature",
                      "min_temperature", "telegram"]


class ObservationIn(BaseModel):
    """Тіло POST: нове спостереження (наприклад, з автоматичної станції)."""
    time: datetime
    temperature: float = Field(ge=-80, le=60)
    pressure: Optional[float] = Field(None, ge=850, le=1100)
    wind_speed: Optional[float] = Field(None, ge=0, le=75)


class ObservationPatch(BaseModel):
    """Тіло PATCH: лише поля, які змінюємо (виправлення помилки оператора)."""
    temperature: Optional[float] = Field(None, ge=-80, le=60)
    pressure: Optional[float] = Field(None, ge=850, le=1100)
    wind_speed: Optional[float] = Field(None, ge=0, le=75)


class ImportIn(BaseModel):
    """Тіло POST /imports: телеграми у форматі ogimet getsynop (CSV)."""
    csv: str


def to_json(obs, fields=None):
    data = {**obs, "time": format_time(obs["time"])}
    data = {key: data.get(key) for key in OBSERVATION_FIELDS}
    if fields:
        data = {key: data[key] for key in fields}
    return data


def page(items, limit, offset, request):
    """Конверт сторінки: елементи + загальна кількість + посилання на наступну."""
    chunk = items[offset:offset + limit]
    next_url = None
    if offset + limit < len(items):
        next_url = str(request.url.include_query_params(offset=offset + limit, limit=limit))
    return {"items": chunk, "total": len(items), "limit": limit, "offset": offset, "next": next_url}


def create_app(repo=None, with_api_types=True):
    repo = repo or MeteoRepository.default()
    imports = {}                                    # id → стан фонового імпорту
    app = FastAPI(title="Meteo API", version="2.0.0",
                  description="REST API метеостанцій України — навчальний приклад уроку 32")
    app.state.repo = repo

    @app.exception_handler(NotFoundError)
    def not_found(request, error):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ConflictError)
    def conflict(request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    def parse_fields(fields):
        if not fields:
            return None
        names = [name.strip() for name in fields.split(",")]
        unknown = [name for name in names if name not in OBSERVATION_FIELDS]
        if unknown:
            raise HTTPException(400, f"невідомі поля: {', '.join(unknown)}")
        return names

    # ---------- станції ----------
    @app.get("/api/v1/stations")
    def list_stations(request: Request, limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)):
        return page(repo.list_stations(), limit, offset, request)

    @app.get("/api/v1/stations/{wmo}")
    def get_station(wmo: str):
        return repo.get_station(wmo)

    # ---------- спостереження ----------
    @app.get("/api/v1/stations/{wmo}/observations")
    def list_observations(request: Request, wmo: str,
                          date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
                          hour: Optional[int] = Query(None, ge=0, le=23), fields: Optional[str] = None,
                          limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0)):
        names = parse_fields(fields)
        items = repo.list_observations(
            wmo,
            parse_time(date_from.isoformat()) if date_from else None,
            parse_time(date_to.isoformat()) if date_to else None,
            hour,
        )
        return page([to_json(obs, names) for obs in items], limit, offset, request)

    @app.get("/api/v1/stations/{wmo}/observations/{moment}")
    def get_observation(wmo: str, moment: str):
        return to_json(repo.get_observation(wmo, parse_time(moment)))

    @app.post("/api/v1/stations/{wmo}/observations", status_code=201)
    def create_observation(wmo: str, body: ObservationIn, response: Response):
        obs = repo.add_observation({"station": wmo, "time": parse_time(body.time.isoformat()),
                                    **body.model_dump(exclude={"time"})})
        response.headers["Location"] = f"/api/v1/stations/{wmo}/observations/{format_time(obs['time'])}"
        return to_json(obs)

    @app.patch("/api/v1/stations/{wmo}/observations/{moment}")
    def patch_observation(wmo: str, moment: str, body: ObservationPatch):
        changes = body.model_dump(exclude_unset=True)
        return to_json(repo.update_observation(wmo, parse_time(moment), changes))

    @app.delete("/api/v1/stations/{wmo}/observations/{moment}", status_code=204)
    def delete_observation(wmo: str, moment: str):
        repo.delete_observation(wmo, parse_time(moment))

    @app.get("/api/v1/observations/latest")
    def latest(fields: Optional[str] = None):
        names = parse_fields(fields)
        return {"items": [{**to_json(obs, names), "station_name": repo.get_station(obs["station"])["name"],
                           "lat": repo.get_station(obs["station"])["lat"],
                           "lon": repo.get_station(obs["station"])["lon"]}
                          for obs in repo.latest()]}

    # ---------- імпорт: довга операція → 202 Accepted ----------
    def run_import(job_id, csv_text):
        imports[job_id]["status"] = "running"
        time.sleep(0.2)                              # у справжньому сервісі тут хвилини завантаження з ogimet
        added, skipped = repo.import_records(parse_ogimet_csv(csv_text.splitlines()))
        imports[job_id].update(status="done", added=added, skipped=skipped)

    @app.post("/api/v1/imports", status_code=202)
    def create_import(body: ImportIn, response: Response, background: BackgroundTasks):
        job_id = uuid.uuid4().hex[:8]
        imports[job_id] = {"id": job_id, "status": "queued"}
        background.add_task(run_import, job_id, body.csv)
        response.headers["Location"] = f"/api/v1/imports/{job_id}"
        return imports[job_id]

    @app.get("/api/v1/imports/{job_id}")
    def get_import(job_id: str):
        if job_id not in imports:
            raise HTTPException(404, f"імпорт {job_id} не знайдено")
        return imports[job_id]

    if with_api_types:                               # RPC, GraphQL, SOAP, WebSocket, SSE, webhook
        from . import api_types
        api_types.install(app, repo)
    return app


app = create_app()
_server = None


def start_server(port=8032, application=None):
    """Запустити API у фоновому потоці (один раз) і повернути його адресу."""
    global _server
    import uvicorn

    if _server is None:
        config = uvicorn.Config(application or app, host="127.0.0.1", port=port, log_level="warning")
        _server = uvicorn.Server(config)
        threading.Thread(target=_server.run, daemon=True).start()
        while not _server.started:
            time.sleep(0.05)
    return f"http://127.0.0.1:{port}"
