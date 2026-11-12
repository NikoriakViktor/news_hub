"""Повтори з паузою: що повторювати, скільки чекати, і чому POST повторювати не можна."""
import random
import time

import httpx

from server import start_server

BASE = start_server()

RETRY_STATUSES = {429, 502, 503, 504}           # «спробуй пізніше»; 4xx інші — помилка запиту, повтор не допоможе
SAFE_TO_RETRY = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}   # ідемпотентні методи


def request_with_retry(client: httpx.Client, method: str, url: str, *,
                       attempts: int = 4, base: float = 0.2, cap: float = 2.0, **kwargs) -> httpx.Response:
    if method not in SAFE_TO_RETRY:
        attempts = 1                             # POST/PATCH: повтор може створити дубль
    for attempt in range(1, attempts + 1):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code not in RETRY_STATUSES or attempt == attempts:
                return response
            reason = str(response.status_code)
            retry_after = response.headers.get("Retry-After")
        except httpx.TransportError as error:   # ConnectError, ReadTimeout, …
            if attempt == attempts:
                raise
            reason, retry_after = type(error).__name__, None
        pause = min(cap, base * 2 ** (attempt - 1)) * random.uniform(0.5, 1)    # backoff + jitter
        if retry_after and retry_after.isdigit():
            pause = max(pause, float(retry_after))                              # сервер сказав, скільки чекати
        print(f"  спроба {attempt}: {reason}, чекаю {pause:.2f} с")
        time.sleep(pause)
    raise AssertionError("недосяжно")


with httpx.Client(base_url=BASE, timeout=1) as client:
    print("--- GET /flaky: три 503, потім 200")
    client.post("/reset")
    start = time.perf_counter()
    response = request_with_retry(client, "GET", "/flaky", params={"fail": 3})
    print(response.status_code, response.json(), f"за {time.perf_counter() - start:.1f} с")

    print("--- те саме, але сервер надсилає Retry-After: 1")
    client.post("/reset")
    start = time.perf_counter()
    response = request_with_retry(client, "GET", "/flaky", params={"fail": 2, "retry_after": 1})
    print(response.status_code, response.json(), f"за {time.perf_counter() - start:.1f} с")

    print("--- GET /news/42: 404 не повторюємо")
    print(request_with_retry(client, "GET", "/news/42").status_code)

    print("--- POST /orders: сервер відповідає за 1.5 с, тайм-аут 1 с")
    client.post("/reset")
    for _ in range(3):                           # наївний повтор POST «бо тайм-аут»
        try:
            client.post("/orders")
            break
        except httpx.ReadTimeout:
            print("  ReadTimeout — повторюю")
    time.sleep(2)
    print("замовлень на сервері:", client.get("/stats").json()["orders"])

print("--- вбудовані повтори httpx: лише помилки з'єднання")
transport = httpx.HTTPTransport(retries=2)
with httpx.Client(transport=transport, timeout=1) as client:
    client.post(f"{BASE}/reset")
    print("GET /flaky з retries=2:", client.get(f"{BASE}/flaky").status_code)
    start = time.perf_counter()
    try:
        client.get("http://127.0.0.1:8799/")
    except httpx.ConnectError:
        print(f"закритий порт: ConnectError після повторів, {time.perf_counter() - start:.2f} с")
