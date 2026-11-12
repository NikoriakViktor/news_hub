"""Middleware у FastAPI: три способи написати, порядок шарів, чого middleware не бачить, вбудовані класи.

    python middleware_demo.py

Мережі й Redis не потрібні: запити йдуть через TestClient у тому самому процесі.
"""
import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CallNext = Callable[[Request], Awaitable[Response]]


def section(title: str) -> None:
    print(f"--- {title}")


# 1. Три способи написати той самий middleware: заголовок X-Process-Time ------------------------------

async def timing_function(request: Request, call_next: CallNext) -> Response:
    """@app.middleware("http") — функція з call_next."""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.perf_counter() - start) * 1000:.1f}ms"
    return response


class TimingBase(BaseHTTPMiddleware):
    """BaseHTTPMiddleware — те саме, але клас: можна передати параметри в __init__."""

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - start) * 1000:.1f}ms"
        return response


class TimingASGI:
    """Чистий ASGI: (scope, receive, send). Час — до ОСТАННЬОГО шматка тіла, а не до заголовків."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":                       # websocket, lifespan — пропускаємо як є
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                elapsed = (time.perf_counter() - start) * 1000
                message.setdefault("headers", []).append((b"x-time-to-headers", f"{elapsed:.1f}ms".encode()))
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                scope.setdefault("state", {})["total_ms"] = (time.perf_counter() - start) * 1000
            await send(message)

        await self.app(scope, receive, send_wrapper)


def make_app(kind: str) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def chunks():  # type: ignore[no-untyped-def]
            for number in range(3):
                await asyncio.sleep(0.1)
                yield f"chunk {number}\n"
        return StreamingResponse(chunks(), media_type="text/plain")

    if kind == "function":
        app.middleware("http")(timing_function)
    elif kind == "base":
        app.add_middleware(TimingBase)
    else:
        app.add_middleware(TimingASGI)
    return app


def three_ways() -> None:
    section("1. той самий middleware трьома способами")
    for kind in ("function", "base", "asgi"):
        with TestClient(make_app(kind)) as client:
            headers = client.get("/ping").headers
            print(f"{kind:8} X-Process-Time={headers.get('x-process-time')}  "
                  f"X-Time-To-Headers={headers.get('x-time-to-headers')}")


def overhead() -> None:
    """Скільки коштує сам шар: прямі виклики ASGI без мережі й без TestClient."""
    section("2. ціна шару: 3000 запитів напряму в ASGI")

    async def call(app: ASGIApp) -> None:
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                 "scheme": "http", "path": "/ping", "raw_path": b"/ping", "query_string": b"",
                 "root_path": "", "headers": [(b"host", b"test")], "client": ("1.2.3.4", 1), "server": ("test", 80)}

        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            pass

        await app(scope, receive, send)

    async def bench(app: ASGIApp, n: int = 3000) -> float:
        await call(app)                                   # перший виклик будує стек middleware
        start = time.perf_counter()
        for _ in range(n):
            await call(app)
        return (time.perf_counter() - start) / n * 1_000_000

    results = {}
    for kind in ("none", "function", "base", "asgi"):
        app = make_app(kind) if kind != "none" else FastAPI()
        if kind == "none":
            @app.get("/ping")
            async def ping() -> dict[str, bool]:
                return {"ok": True}
        results[kind] = asyncio.run(bench(app))
    for kind, micro in results.items():
        print(f"{kind:8} {micro:6.0f} мкс на запит  (+{micro - results['none']:.0f} мкс до застосунку без middleware)")


# 3. Порядок: цибуля ---------------------------------------------------------------------------------

def onion() -> None:
    section("3. порядок: останній зареєстрований — зовнішній")
    trace: list[str] = []
    app = FastAPI()

    def layer(name: str):  # type: ignore[no-untyped-def]
        async def middleware(request: Request, call_next: CallNext) -> Response:
            trace.append(f"{name}→")
            response = await call_next(request)
            trace.append(f"←{name}")
            return response
        return middleware

    class ClassLayer(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: CallNext) -> Response:
            trace.append("C→")
            response = await call_next(request)
            trace.append("←C")
            return response

    @app.get("/")
    async def endpoint() -> dict[str, bool]:
        trace.append("ендпоінт")
        return {"ok": True}

    app.middleware("http")(layer("A"))       # першим
    app.add_middleware(ClassLayer)          # другим — декоратор і add_middleware в один список
    app.middleware("http")(layer("B"))       # останнім → зовнішній
    with TestClient(app) as client:
        client.get("/")
    print(" ".join(trace))
    print("app.user_middleware:", [m.cls.__name__ if m.cls is not BaseHTTPMiddleware
                                   else f"BaseHTTPMiddleware({m.kwargs['dispatch'].__name__})"
                                   for m in app.user_middleware])


# 4. Чого middleware не бачить ---------------------------------------------------------------------

def blind_spots() -> None:
    section("4. чого middleware не бачить")
    log: list[str] = []
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        if item_id == 0:
            raise HTTPException(404, "немає")
        if item_id == 13:
            raise RuntimeError("баг у коді")
        return {"id": item_id}

    @app.get("/guarded")
    async def guarded() -> dict[str, bool]:
        return {"ok": True}

    @app.middleware("http")
    async def inner(request: Request, call_next: CallNext) -> Response:
        if request.url.path == "/guarded" and request.headers.get("X-Key") != "secret":
            raise HTTPException(401, "потрібен X-Key")       # помилка: тут обробники винятків не діють
        return await call_next(request)

    @app.middleware("http")
    async def outer(request: Request, call_next: CallNext) -> Response:
        log.append(f"до: path_params={request.path_params} route={request.scope.get('route')}")
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        log.append(f"після: {response.status_code} path_params={request.path_params} "
                   f"route={getattr(route, 'path', None)} {type(response).__name__}")
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - start) * 1000:.1f}ms"
        return response

    with TestClient(app, raise_server_exceptions=False) as client:
        for path in ("/items/7", "/items/0", "/items/13", "/guarded"):
            log.clear()
            response = client.get(path)
            print(f"GET {path:10} → {response.status_code} X-Process-Time={response.headers.get('x-process-time')}"
                  f" | {response.text[:40]}")
            for line in log:
                print("   ", line)

    fixed = FastAPI()

    @fixed.get("/boom")
    async def boom() -> None:
        raise RuntimeError("баг у коді")

    @fixed.middleware("http")
    async def logged(request: Request, call_next: CallNext) -> Response:
        start = time.perf_counter()
        try:
            return await call_next(request)
        except Exception as error:                        # зафіксувати й кинути далі: 500 зробить ServerErrorMiddleware
            print(f"    журнал: {request.method} {request.url.path} → виняток {type(error).__name__}"
                  f" за {(time.perf_counter() - start) * 1000:.1f}ms")
            raise

    with TestClient(fixed, raise_server_exceptions=False) as client:
        print("GET /boom з try/except у middleware →", client.get("/boom").status_code)

    probe = FastAPI()

    @probe.get("/")
    async def root() -> dict[str, bool]:
        return {"ok": True}

    @probe.middleware("http")
    async def try_body(request: Request, call_next: CallNext) -> Response:
        response = await call_next(request)
        print("    тип відповіді в call_next:", type(response).__name__,
              "| є .body:", hasattr(response, "body"))
        return response

    with TestClient(probe) as client:
        client.get("/")


def streaming() -> None:
    section("5. стрімінг: функція бачить лише заголовки, ASGI — кінець тіла")
    for kind in ("function", "asgi"):
        app = make_app(kind)
        captured: dict[str, float] = {}
        if kind == "asgi":
            inner = app.build_middleware_stack

            def stack() -> ASGIApp:
                built = inner()

                async def capture(scope: Scope, receive: Receive, send: Send) -> None:
                    await built(scope, receive, send)
                    if "total_ms" in scope.get("state", {}):
                        captured["total"] = scope["state"]["total_ms"]
                return capture
            app.build_middleware_stack = stack  # type: ignore[method-assign]
        with TestClient(app) as client:
            start = time.perf_counter()
            response = client.get("/stream")
            wall = (time.perf_counter() - start) * 1000
        header = response.headers.get("x-process-time") or response.headers.get("x-time-to-headers")
        extra = f" | ASGI до останнього шматка: {captured['total']:.0f}ms" if captured else ""
        print(f"{kind:8} заголовок: {header} | тіло прийшло за {wall:.0f}ms{extra}")


def websocket_scope() -> None:
    section("6. WebSocket: @app.middleware('http') його не бачить")
    seen: list[str] = []
    app = FastAPI()

    @app.middleware("http")
    async def http_only(request: Request, call_next: CallNext) -> Response:
        seen.append(f"http {request.url.path}")
        return await call_next(request)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("hello")
        await websocket.close()

    @app.get("/")
    async def root() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/")
        with client.websocket_connect("/ws") as connection:
            connection.receive_text()
    print("middleware бачив:", seen)


# 7. Вбудовані ---------------------------------------------------------------------------------------

def builtins() -> None:
    section("7. вбудовані: GZip, TrustedHost, HTTPSRedirect")
    app = FastAPI()

    @app.get("/small")
    async def small() -> dict[str, str]:
        return {"text": "коротко"}

    @app.get("/big")
    async def big() -> dict[str, list[str]]:
        return {"items": [f"новина {number}" for number in range(200)]}

    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.example.com", "*.example.com"])
    with TestClient(app, base_url="http://api.example.com") as client:
        for path in ("/small", "/big"):
            response = client.get(path, headers={"Accept-Encoding": "gzip"})
            raw = response.headers.get("content-length")
            print(f"GET {path:6} Accept-Encoding: gzip → content-encoding={response.headers.get('content-encoding')}"
                  f", байтів у мережі={raw}, після розпакування={len(response.content)}")
        response = client.get("/big", headers={"Accept-Encoding": "identity"})
        print(f"GET /big    без gzip у запиті → content-encoding={response.headers.get('content-encoding')}"
              f", байтів={response.headers.get('content-length')}")
        for host in ("api.example.com", "news.example.com", "evil.test"):
            response = client.get("/small", headers={"Host": host})
            print(f"Host: {host:17} → {response.status_code} {response.text[:30]}")

    redirect = FastAPI()

    @redirect.get("/api/news")
    async def news() -> dict[str, bool]:
        return {"ok": True}

    redirect.add_middleware(HTTPSRedirectMiddleware)
    with TestClient(redirect, base_url="http://api.example.com", follow_redirects=False) as client:
        response = client.get("/api/news?page=2")
        print(f"http://…/api/news?page=2 → {response.status_code} Location: {response.headers['location']}")
    with TestClient(redirect, base_url="https://api.example.com") as client:
        print("https://…/api/news →", client.get("/api/news").status_code)


if __name__ == "__main__":
    three_ways()
    overhead()
    onion()
    blind_spots()
    streaming()
    websocket_scope()
    builtins()
