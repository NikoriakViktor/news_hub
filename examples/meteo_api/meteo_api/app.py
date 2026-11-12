"""Meteo API v2 — REST-версія першого метео-API (legacy/).

Було (legacy/main.py): /download_telegrams, POST /filter_telegrams/, /telegram/{collection}/{id}.
Стало: ресурси «станції» і «спостереження», методи HTTP за призначенням, чесні статус-коди.
Виправлення після рецензії:
- час в адресі — `moment: datetime`: «/observations/вчора» дає 422 від FastAPI, а не 500;
- `PATCH {"temperature": null}` — 422: температура обов'язкова й у POST; тиск і вітер можна стерти null-ом,
  бо й у POST їх може не бути;
- зламаний CSV імпорту — 422 одразу з номером рядка; несподівана помилка у фоні — статус `failed`, а не
  вічне `running`;
- невідомі поля в тілі (`extra="forbid"`) — 422, а не мовчки відкинуті;
- `response_model` і задокументовані 404/409/422 — схеми в OpenAPI замість `{}`;
- невідоме поле в `fields=` — 422 у форматі FastAPI, як і решта помилок параметрів (було 400).

    uvicorn meteo_api.app:app --port 8032          # Swagger: http://127.0.0.1:8032/docs

або з Python / Jupyter:

    from meteo_api.app import start_server
    BASE = start_server()                          # http://127.0.0.1:8032, сервер у фоновому потоці
"""
import threading
import time
import uuid
from datetime import datetime
from typing import Literal, Optional, Union

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .storage import ConflictError, MeteoRepository, NotFoundError, format_time, parse_ogimet_csv, parse_time

OBSERVATION_FIELDS = ["station", "time", "temperature", "dew_point", "relative_humidity", "wind_dir",
                      "wind_speed", "pressure", "sea_level_pressure", "max_temperature",
                      "min_temperature", "telegram"]


class ObservationIn(BaseModel):
    """Тіло POST: нове спостереження (наприклад, з автоматичної станції)."""
    model_config = ConfigDict(extra="forbid")      # «dew_point»: 12 → 422, а не мовчки загублене значення

    time: datetime
    temperature: float = Field(ge=-80, le=60)
    pressure: Optional[float] = Field(None, ge=850, le=1100)
    wind_speed: Optional[float] = Field(None, ge=0, le=75)


class ObservationPatch(BaseModel):
    """Тіло PATCH: лише поля, які змінюємо (виправлення помилки оператора)."""
    model_config = ConfigDict(extra="forbid")

    temperature: Optional[float] = Field(None, ge=-80, le=60)
    pressure: Optional[float] = Field(None, ge=850, le=1100)
    wind_speed: Optional[float] = Field(None, ge=0, le=75)

    @field_validator("temperature")
    @classmethod
    def temperature_not_null(cls, value: Optional[float]) -> float:
        """Поле не передали — його не змінюють; передали null — помилка, а не стерта температура."""
        if value is None:
            raise ValueError("температура не може бути null; не хочеш міняти — не передавай її")
        return value


class ImportIn(BaseModel):
    """Тіло POST /imports: телеграми у форматі ogimet getsynop (CSV)."""
    model_config = ConfigDict(extra="forbid")

    csv: str


class Station(BaseModel):
    wmo: str
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    elevation: Optional[float] = None


class Observation(BaseModel):
    """Спостереження у відповіді. З `fields=` — лише вибрані поля (решти у відповіді немає)."""
    station: Optional[str] = None
    time: Optional[str] = None
    temperature: Optional[float] = None
    dew_point: Optional[float] = None
    relative_humidity: Optional[Union[int, float]] = None   # Union: 47 лишається 47, а не 47.0
    wind_dir: Optional[Union[int, float]] = None
    wind_speed: Optional[Union[int, float]] = None
    pressure: Optional[float] = None
    sea_level_pressure: Optional[float] = None
    max_temperature: Optional[float] = None
    min_temperature: Optional[float] = None
    telegram: Optional[str] = None


class LatestObservation(Observation):
    station_name: str
    lat: Optional[float] = None
    lon: Optional[float] = None


class StationPage(BaseModel):
    items: list[Station]
    total: int
    limit: int
    offset: int
    next: Optional[str]


class ObservationPage(BaseModel):
    items: list[Observation]
    total: int
    limit: int
    offset: int
    next: Optional[str]


class LatestList(BaseModel):
    items: list[LatestObservation]


class ImportJob(BaseModel):
    id: str
    status: Literal["queued", "running", "done", "failed"]
    added: Optional[int] = None
    skipped: Optional[int] = None
    error: Optional[str] = None


class ErrorOut(BaseModel):
    detail: str


NOT_FOUND = {404: {"model": ErrorOut, "description": "станції чи спостереження немає"}}
CONFLICT = {409: {"model": ErrorOut, "description": "спостереження на цей час уже є"}}


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
                  description="REST API метеостанцій України — навчальний приклад")
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
        if unknown:                  # той самий формат 422, що й для решти помилок параметрів
            raise HTTPException(422, [{"type": "value_error", "loc": ["query", "fields"],
                                       "msg": f"невідомі поля: {', '.join(unknown)}; є: {', '.join(OBSERVATION_FIELDS)}",
                                       "input": fields}])
        return names

    def utc(moment):
        return parse_time(moment.isoformat())

    # ---------- станції ----------
    @app.get("/api/v1/stations", response_model=StationPage)
    def list_stations(request: Request, limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)):
        return page(repo.list_stations(), limit, offset, request)

    @app.get("/api/v1/stations/{wmo}", response_model=Station, responses=NOT_FOUND)
    def get_station(wmo: str):
        return repo.get_station(wmo)

    # ---------- спостереження ----------
    @app.get("/api/v1/stations/{wmo}/observations", response_model=ObservationPage,
             response_model_exclude_unset=True, responses=NOT_FOUND)
    def list_observations(request: Request, wmo: str,
                          date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
                          hour: Optional[int] = Query(None, ge=0, le=23), fields: Optional[str] = None,
                          limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0)):
        names = parse_fields(fields)
        items = repo.list_observations(
            wmo,
            utc(date_from) if date_from else None,
            utc(date_to) if date_to else None,
            hour,
        )
        return page([to_json(obs, names) for obs in items], limit, offset, request)

    @app.get("/api/v1/stations/{wmo}/observations/{moment}", response_model=Observation, responses=NOT_FOUND)
    def get_observation(wmo: str, moment: datetime):
        return to_json(repo.get_observation(wmo, utc(moment)))

    @app.post("/api/v1/stations/{wmo}/observations", status_code=201, response_model=Observation,
              responses={**NOT_FOUND, **CONFLICT})
    def create_observation(wmo: str, body: ObservationIn, response: Response):
        obs = repo.add_observation({"station": wmo, "time": utc(body.time),
                                    **body.model_dump(exclude={"time"})})
        response.headers["Location"] = f"/api/v1/stations/{wmo}/observations/{format_time(obs['time'])}"
        return to_json(obs)

    @app.patch("/api/v1/stations/{wmo}/observations/{moment}", response_model=Observation, responses=NOT_FOUND)
    def patch_observation(wmo: str, moment: datetime, body: ObservationPatch):
        changes = body.model_dump(exclude_unset=True)
        return to_json(repo.update_observation(wmo, utc(moment), changes))

    @app.delete("/api/v1/stations/{wmo}/observations/{moment}", status_code=204, responses=NOT_FOUND)
    def delete_observation(wmo: str, moment: datetime):
        repo.delete_observation(wmo, utc(moment))

    @app.get("/api/v1/observations/latest", response_model=LatestList, response_model_exclude_unset=True)
    def latest(fields: Optional[str] = None):
        names = parse_fields(fields)
        return {"items": [{**to_json(obs, names), "station_name": repo.get_station(obs["station"])["name"],
                           "lat": repo.get_station(obs["station"])["lat"],
                           "lon": repo.get_station(obs["station"])["lon"]}
                          for obs in repo.latest()]}

    # ---------- імпорт: довга операція → 202 Accepted ----------
    def run_import(job_id, records):
        imports[job_id]["status"] = "running"
        time.sleep(0.2)                              # у справжньому сервісі тут хвилини завантаження з ogimet
        try:
            added, skipped = repo.import_records(records)
        except Exception as error:                   # фонова задача: помилку ніхто не побачить, крім статусу
            imports[job_id].update(status="failed", error=f"{type(error).__name__}: {error}")
            return
        imports[job_id].update(status="done", added=added, skipped=skipped)

    @app.post("/api/v1/imports", status_code=202, response_model=ImportJob, response_model_exclude_none=True,
              responses={422: {"description": "тіло не JSON за схемою або CSV зламаний (номер рядка в detail)"}})
    def create_import(body: ImportIn, response: Response, background: BackgroundTasks):
        try:                                         # формат перевіряємо до 202: клієнт дізнається одразу
            records = parse_ogimet_csv(body.csv.splitlines())
        except ValueError as error:
            raise HTTPException(422, [{"type": "value_error", "loc": ["body", "csv"], "msg": str(error)}]) from None
        job_id = uuid.uuid4().hex[:8]
        imports[job_id] = {"id": job_id, "status": "queued"}
        background.add_task(run_import, job_id, records)
        response.headers["Location"] = f"/api/v1/imports/{job_id}"
        return imports[job_id]

    @app.get("/api/v1/imports/{job_id}", response_model=ImportJob, response_model_exclude_none=True,
             responses={404: {"model": ErrorOut, "description": "такого імпорту немає"}})
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
