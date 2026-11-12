"""Свій клієнт до чужого API: адреса, тайм-аут, повтори й перетворення кодів на свої винятки — в одному класі."""
import time
from types import TracebackType

import httpx
import requests

from server import start_server

BASE = start_server()


class NewsAPIError(Exception):
    """Будь-яка помилка чужого API новин."""


class NotFound(NewsAPIError):
    pass


class NewsAPIClient:
    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 5,
                 retries: int = 3, pause: float = 0.2, transport: httpx.BaseTransport | None = None) -> None:
        headers = {"User-Agent": "news_hub/1.0 (+https://github.com/NikoriakViktor/news_hub)"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(base_url=base_url, timeout=timeout, headers=headers, transport=transport)
        self._retries = retries
        self._pause = pause

    def __enter__(self) -> "NewsAPIClient":
        return self

    def __exit__(self, *exc: type[BaseException] | BaseException | TracebackType | None) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        attempts = self._retries if method == "GET" else 1       # POST не повторюємо: можна створити дубль
        for attempt in range(1, attempts + 1):
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.TransportError as error:
                if attempt == attempts:
                    raise NewsAPIError(f"{method} {path}: {type(error).__name__}") from error
            else:
                if response.status_code < 500 or attempt == attempts:
                    break
            time.sleep(self._pause * 2 ** (attempt - 1))

        if response.status_code == 404:
            raise NotFound(response.json()["detail"])
        if response.is_error:
            raise NewsAPIError(f"{method} {path}: HTTP {response.status_code}")
        return response.json()

    def news(self) -> list[dict]:
        return self._request("GET", "/news")

    def one(self, news_id: int) -> dict:
        return self._request("GET", f"/news/{news_id}")

    def flaky(self) -> dict:
        return self._request("GET", "/flaky")


with NewsAPIClient(BASE) as api:
    print([item["title"] for item in api.news()])
    try:
        api.one(42)
    except NotFound as error:
        print("NotFound:", error)
    requests.post(f"{BASE}/reset", timeout=5)
    print("flaky після повторів:", api.flaky())

with NewsAPIClient("http://127.0.0.1:8799", retries=2) as api:
    try:
        api.news()
    except NewsAPIError as error:
        print("NewsAPIError:", error, "| причина:", type(error.__cause__).__name__)

print("--- знайди помилку")


def news_title(news_id: int) -> str:
    response = requests.get(f"{BASE}/news/{news_id}")
    return response.json()["title"]


print(news_title(2))
try:
    print(news_title(42))
except KeyError as error:
    print("KeyError:", error)
