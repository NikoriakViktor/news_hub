"""Клієнт до Meteo API v2 — той самий шаблон, що SmachnoClient в уроці 31.

Streamlit-застосунок і ноутбук говорять з API лише через цей клас:
адреса, тайм-аут, пагінація й перетворення помилок — в одному місці.
"""
import requests


class MeteoError(Exception):
    pass


class StationNotFound(MeteoError):
    pass


class MeteoClient:
    def __init__(self, base_url, timeout=5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.last_exchange = None              # для «HTTP-інспектора»: що саме пішло й прийшло

    def _get(self, path, **params):
        try:
            response = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        except requests.RequestException as error:
            raise MeteoError(f"API недоступний: {type(error).__name__}") from error
        self.last_exchange = {
            "request": f"{response.request.method} {response.request.url}",
            "status": response.status_code,
            "elapsed_ms": round(response.elapsed.total_seconds() * 1000, 1),
            "response_headers": dict(response.headers),
        }
        if response.status_code == 404:
            raise StationNotFound(response.json()["detail"])
        if not response.ok:
            raise MeteoError(f"GET {path}: {response.status_code}")
        return response.json()

    def stations(self):
        """Усі станції: проходимо сторінки, поки є посилання next."""
        items, offset = [], 0
        while True:
            page = self._get("/api/v1/stations", limit=100, offset=offset)
            items += page["items"]
            if page["next"] is None:
                return items
            offset += page["limit"]

    def latest(self):
        return self._get("/api/v1/observations/latest")["items"]

    def observations(self, wmo, fields="time,temperature,pressure,wind_speed"):
        items, offset = [], 0
        while True:
            page = self._get(f"/api/v1/stations/{wmo}/observations", fields=fields, limit=200, offset=offset)
            items += page["items"]
            if page["next"] is None:
                return items
            offset += page["limit"]
