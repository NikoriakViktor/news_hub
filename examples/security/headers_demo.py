"""Секрети, заголовки безпеки, TrustedHost, HTTPS і IP клієнта за проксі, журнали без секретів, ліміт входу.

python headers_demo.py — секрети генеруються тут; запити — через httpx.ASGITransport (без мережі),
адреса клієнта задається параметром `client=`, як її бачив би uvicorn.
"""
import asyncio
import logging
import re
import secrets
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from jwt.warnings import InsecureKeyLengthWarning
from fastapi import FastAPI, Request
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


def title(text: str) -> None:
    print(f"--- {text}")


# ---------------------------------------------------------------------------
title("1. слабкий секрет JWT ламається офлайн")
weak = "change-me"
warnings.simplefilter("ignore", InsecureKeyLengthWarning)    # PyJWT попереджає про короткий ключ — у журнал, який ніхто не читає
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always", InsecureKeyLengthWarning)
    jwt.encode({"sub": "x"}, weak, algorithm="HS256")
print("   PyJWT:", caught[0].category.__name__, "—", str(caught[0].message)[:60] + "…")
token = jwt.encode({"sub": "olena", "role": "user"}, weak, algorithm="HS256")          # перехоплений токен
wordlist = ["secret", "password", "admin", "jwt-secret", "change-me", "changeme"] + [f"key{n}" for n in range(20_000)]
for n, guess in enumerate(wordlist, 1):
    try:
        jwt.decode(token, guess, algorithms=["HS256"])
    except jwt.InvalidSignatureError:
        continue
    forged = jwt.encode({"sub": "olena", "role": "admin"}, guess, algorithm="HS256")
    print(f"   секрет знайдено за {n} спроб: {guess!r}; підроблено role=admin:",
          jwt.decode(forged, weak, algorithms=["HS256"])["role"])
    break
strong = secrets.token_urlsafe(32)
print(f"   secrets.token_urlsafe(32): {len(strong)} символів, 256 біт випадковості")

# ---------------------------------------------------------------------------
title("2. ротація ключа JWT через kid")
keys = {"2026-10": secrets.token_urlsafe(32), "2026-11": secrets.token_urlsafe(32)}
CURRENT = "2026-11"


def sign(claims: dict, kid: str = CURRENT) -> str:
    return jwt.encode(claims, keys[kid], algorithm="HS256", headers={"kid": kid})


def verify(token: str) -> dict:
    kid = jwt.get_unverified_header(token).get("kid")       # заголовок ще не перевірено: лише вибір ключа зі СВОГО словника
    if kid not in keys:
        raise jwt.InvalidTokenError(f"невідомий kid {kid!r}")
    return jwt.decode(token, keys[kid], algorithms=["HS256"])


exp = datetime.now(timezone.utc) + timedelta(minutes=5)
old_token, new_token = sign({"sub": "olena", "exp": exp}, "2026-10"), sign({"sub": "olena", "exp": exp})
print("   під час ротації: старий →", verify(old_token)["sub"], "| новий →", verify(new_token)["sub"])
del keys["2026-10"]                                          # минув строк життя старих токенів
for name, tok in (("старий після видалення ключа", old_token), ("kid=../../etc/passwd", sign({"sub": "x"}).replace(
        jwt.utils.base64url_encode(b'{"alg":"HS256","kid":"2026-11","typ":"JWT"}').decode(),
        jwt.utils.base64url_encode(b'{"alg":"HS256","kid":"../../etc/passwd","typ":"JWT"}').decode()))):
    try:
        verify(tok)
    except jwt.InvalidTokenError as error:
        print(f"   {name}: {type(error).__name__} — {error}")


# ---------------------------------------------------------------------------
def build_app(*, docs: bool, trusted: list[str] | None, https_redirect: bool, proxies: list[str] | None) -> FastAPI:
    app = FastAPI(docs_url="/docs" if docs else None, redoc_url=None, openapi_url="/openapi.json" if docs else None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if not request.url.path.startswith("/docs"):         # Swagger UI тягне скрипти з CDN — суворий CSP його зламає
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            response.headers.setdefault("Cache-Control", "no-store")
        if request.url.scheme == "https":                    # HSTS має сенс лише у відповіді по HTTPS
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.get("/api/me")
    def me(request: Request) -> dict[str, str]:
        return {"client": request.client.host, "scheme": request.url.scheme}

    @app.post("/api/password-reset", name="reset")
    def reset(request: Request) -> dict[str, str]:
        return {"link": str(request.url_for("reset_confirm", token="t0k3n"))}  # лист піде з цим посиланням

    @app.get("/reset/{token}", name="reset_confirm")
    def reset_confirm(token: str) -> dict[str, str]:
        return {"token": token}

    if https_redirect:
        app.add_middleware(HTTPSRedirectMiddleware)
    if trusted:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted)
    if proxies is not None:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=proxies)  # останнім = зовнішнім: решта бачить уже справжні дані
    return app


async def call(app: FastAPI, method: str, url: str, client: str = "203.0.113.7", **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=(client, 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://api.example.com") as http:
        return await http.request(method, url, **kwargs)


async def web() -> None:
    title("3. заголовки безпеки")
    dev = build_app(docs=True, trusted=None, https_redirect=False, proxies=None)
    r = await call(dev, "GET", "/api/me")
    print("   /api/me:", {k: v for k, v in r.headers.items() if k.startswith(("x-", "referrer", "content-sec", "cache"))})
    r = await call(dev, "GET", "/docs")
    print("   /docs: CSP:", r.headers.get("content-security-policy"), "| зовнішні скрипти:",
          sorted(set(re.findall(r'src="(https://[^/"]+)', r.text))))
    prod = build_app(docs=False, trusted=None, https_redirect=False, proxies=None)
    print("   docs_url=None: /docs →", (await call(prod, "GET", "/docs")).status_code,
          "| /openapi.json →", (await call(prod, "GET", "/openapi.json")).status_code)

    title("4. Host-заголовок і TrustedHostMiddleware")
    bare = build_app(docs=False, trusted=None, https_redirect=False, proxies=None)
    r = await call(bare, "POST", "/api/password-reset", headers={"Host": "evil.example"})
    print("   без TrustedHost, Host: evil.example →", r.status_code, r.json())
    guarded = build_app(docs=False, trusted=["api.example.com"], https_redirect=False, proxies=None)
    r = await call(guarded, "POST", "/api/password-reset", headers={"Host": "evil.example"})
    print("   з TrustedHost,   Host: evil.example →", r.status_code, r.text)
    r = await call(guarded, "POST", "/api/password-reset")
    print("   з TrustedHost,   Host: api.example.com →", r.status_code, r.json())

    title("5. за проксі: IP клієнта і схема")
    spoof = {"X-Forwarded-For": "1.2.3.4", "X-Forwarded-Proto": "https"}
    for label, proxies, client in (("ProxyHeaders не підключено", None, "172.28.0.10"),
                                   ("напряму від клієнта, довіряємо nginx", ["172.28.0.10"], "203.0.113.7"),
                                   ("через nginx (172.28.0.10)", ["172.28.0.10"], "172.28.0.10"),
                                   ("trusted_hosts='*', напряму", ["*"], "203.0.113.7")):
        app = build_app(docs=False, trusted=None, https_redirect=False, proxies=proxies)
        r = await call(app, "GET", "/api/me", client=client, headers=spoof)
        print(f"   {label:38} → {r.json()} HSTS: {'strict-transport-security' in r.headers}")
    many = {"X-Forwarded-For": "1.2.3.4, 198.51.100.9", "X-Forwarded-Proto": "https"}
    app = build_app(docs=False, trusted=None, https_redirect=False, proxies=["172.28.0.10"])
    r = await call(app, "GET", "/api/me", client="172.28.0.10", headers=many)
    print(f"   {'XFF «підробка, справжній» через nginx':38} → {r.json()}")

    title("6. HTTPSRedirectMiddleware за проксі")
    loop = build_app(docs=False, trusted=None, https_redirect=True, proxies=None)
    r = await call(loop, "GET", "/api/me", client="172.28.0.10", headers={"X-Forwarded-Proto": "https"})
    print("   без ProxyHeaders, nginx уже зняв TLS →", r.status_code, r.headers.get("location"), "(і так щоразу)")
    ok = build_app(docs=False, trusted=None, https_redirect=True, proxies=["172.28.0.10"])
    r = await call(ok, "GET", "/api/me", client="172.28.0.10", headers={"X-Forwarded-Proto": "https"})
    print("   з ProxyHeaders                        →", r.status_code, r.json())


asyncio.run(web())

# ---------------------------------------------------------------------------
title("7. журнали без секретів")


class RedactSecrets(logging.Filter):
    PATTERNS = [(re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***"),
                (re.compile(r"((?:token|password|secret|api_key)=)[^&\s]+", re.I), r"\1***")]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            message = pattern.sub(replacement, message)
        record.msg, record.args = message, None
        return True


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("   %(levelname)s %(message)s"))
log = logging.getLogger("demo")
log.addHandler(handler)
log.setLevel(logging.INFO)
access = jwt.encode({"sub": "olena"}, strong, algorithm="HS256")
headers = {"authorization": f"Bearer {access}", "user-agent": "curl/8"}
log.info('"GET /reset?token=%s HTTP/1.1" 200', "t0k3n-from-email")
log.info("headers=%s", headers)
handler.addFilter(RedactSecrets())
log.info('"GET /reset?token=%s HTTP/1.1" 200', "t0k3n-from-email")
log.info("headers=%s", headers)

# ---------------------------------------------------------------------------
title("8. ліміт входу: ключ — IP, ім'я чи обидва")
LIMIT = 5


def attack(attempts: list[tuple[str, str]]) -> dict[str, int]:
    by_ip, by_user, blocked = defaultdict(int), defaultdict(int), {"ip": 0, "user": 0}
    for ip, user in attempts:
        by_ip[ip] += 1
        by_user[user] += 1
        blocked["ip"] += by_ip[ip] > LIMIT
        blocked["user"] += by_user[user] > LIMIT
    return blocked


stuffing = [(f"198.51.100.{n}", "olena") for n in range(1, 21)]                     # 20 IP, один акаунт
spraying = [("203.0.113.7", f"user{n}") for n in range(1, 21)]                       # один IP, 20 акаунтів
print("   20 спроб з 20 IP на olena     → заблоковано", attack(stuffing))
print("   20 спроб з одного IP на 20 імен → заблоковано", attack(spraying))
