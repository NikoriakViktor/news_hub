"""Вхідні webhook: підпис HMAC у стилі GitHub і Stripe, секретний заголовок Telegram, повтори й ротація секрету.

python webhooks_demo.py — секрети генеруються тут; відправника імітує сам скрипт; лише TestClient.

Формати — за документацією провайдерів:
- GitHub: X-Hub-Signature-256: sha256=<hex HMAC-SHA256(secret, body)>, X-GitHub-Delivery: <id доставки>;
- Stripe: Stripe-Signature: t=<час>,v1=<hex HMAC-SHA256(secret, "<час>." + body)>[,v1=...];
- Telegram: X-Telegram-Bot-Api-Secret-Token: <secret_token з setWebhook>.
"""
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Iterable

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

GITHUB_SECRET = secrets.token_hex(32).encode()
STRIPE_SECRETS = [secrets.token_hex(32).encode()]          # під час ротації — два: новий і старий
TELEGRAM_SECRET = secrets.token_urlsafe(32)                  # Telegram: 1–256 символів A-Z a-z 0-9 _ -
TOLERANCE = 300

app = FastAPI()
processed: dict[str, list[str]] = {"github": [], "stripe": [], "naive": []}
seen_deliveries: set[str] = set()
seen_events: set[str] = set()


def hmac_hex(secret: bytes, data: bytes) -> str:
    return hmac.new(secret, data, hashlib.sha256).hexdigest()


# --- GitHub-стиль: підпис тіла, без часу; повтор — за id доставки -------------------------------------
@app.post("/github")
async def github(request: Request) -> dict[str, str]:
    body = await request.body()                                         # СИРІ байти — до json
    expected = "sha256=" + hmac_hex(GITHUB_SECRET, body)
    received = request.headers.get("X-Hub-Signature-256", "")
    if not hmac.compare_digest(received.encode(), expected.encode()):
        raise HTTPException(401, detail="підпис не збігається")
    delivery = request.headers.get("X-GitHub-Delivery", "")
    if delivery in seen_deliveries:
        return {"status": "уже оброблено"}                              # 2xx: інакше відправник повторюватиме
    seen_deliveries.add(delivery)
    processed["github"].append(json.loads(body)["action"])
    return {"status": "ok"}


# --- Stripe-стиль: час у підписі, кілька v1 (ротація), ідемпотентність за id події -------------------
def parse_stripe_header(header: str) -> tuple[int, list[str]]:
    items = [part.split("=", 1) for part in header.split(",") if "=" in part]
    timestamps = [value for key, value in items if key == "t"]
    if len(timestamps) != 1 or not (timestamps[0].isascii() and timestamps[0].isdigit()):
        raise HTTPException(401, detail="немає часу в підписі")
    return int(timestamps[0]), [value for key, value in items if key == "v1"]


def stripe_valid(secrets_: Iterable[bytes], timestamp: int, signatures: list[str], body: bytes) -> bool:
    signed = str(timestamp).encode() + b"." + body
    return any(hmac.compare_digest(sig.encode(), hmac_hex(secret, signed).encode())
               for secret in secrets_ for sig in signatures)


@app.post("/stripe")
async def stripe(request: Request) -> dict[str, str]:
    body = await request.body()
    timestamp, signatures = parse_stripe_header(request.headers.get("Stripe-Signature", ""))
    if abs(time.time() - timestamp) > TOLERANCE:
        raise HTTPException(401, detail=f"підпис старший за {TOLERANCE} с")
    if not stripe_valid(STRIPE_SECRETS, timestamp, signatures, body):
        raise HTTPException(401, detail="підпис не збігається")
    event = json.loads(body)
    if event["id"] in seen_events:
        return {"status": "уже оброблено"}
    seen_events.add(event["id"])
    processed["stripe"].append(event["type"])
    return {"status": "ok"}


# --- помилка: підпис від перезібраного JSON ---------------------------------------------------------
@app.post("/naive")
async def naive(request: Request) -> dict[str, str]:
    data = await request.json()
    body = json.dumps(data).encode()                                   # «ті самі дані» — інші байти
    if not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", "").encode(),
                               ("sha256=" + hmac_hex(GITHUB_SECRET, body)).encode()):
        raise HTTPException(401, detail="підпис не збігається")
    processed["naive"].append(data["action"])
    return {"status": "ok"}


# --- Telegram: підпису немає, лише секретний заголовок ----------------------------------------------
@app.post("/telegram")
async def telegram(request: Request) -> dict[str, bool]:
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if received is None or not hmac.compare_digest(received.encode(), TELEGRAM_SECRET.encode()):
        raise HTTPException(401, detail="неправильний секрет")
    return {"ok": True}


api = TestClient(app)


def title(text: str) -> None:
    print(f"--- {text}")


def show(label: str, response) -> None:
    print(f"   {label:42} → {response.status_code} {response.json()}")


def github_headers(body: bytes, delivery: str, secret: bytes = GITHUB_SECRET) -> dict[str, str]:
    return {"X-Hub-Signature-256": "sha256=" + hmac_hex(secret, body), "X-GitHub-Delivery": delivery,
            "Content-Type": "application/json"}


def stripe_headers(body: bytes, ts: int | None = None, keys: Iterable[bytes] | None = None) -> dict[str, str]:
    ts = int(time.time()) if ts is None else ts
    parts = [f"t={ts}"] + [f"v1={hmac_hex(k, str(ts).encode() + b'.' + body)}" for k in (keys or STRIPE_SECRETS)]
    return {"Stripe-Signature": ",".join(parts), "Content-Type": "application/json"}


title("1. GitHub-стиль: підпис сирого тіла")
body = b'{"action": "opened", "number": 7}'
h = github_headers(body, "delivery-1")
print("   X-Hub-Signature-256:", h["X-Hub-Signature-256"][:19] + "…", "| довжина", len(h["X-Hub-Signature-256"]))
show("справжній", api.post("/github", content=body, headers=h))
show("та сама доставка ще раз (повтор провайдера)", api.post("/github", content=body, headers=h))
show("перехоплений, тіло змінено", api.post("/github", content=b'{"action": "deleted", "number": 7}', headers=h))
show("чужий секрет", api.post("/github", content=body,
                               headers=github_headers(body, "delivery-2", secrets.token_bytes(32))))
upper = {**h, "X-Hub-Signature-256": h["X-Hub-Signature-256"].upper(), "X-GitHub-Delivery": "delivery-3"}
show("той самий hex ВЕЛИКИМИ літерами", api.post("/github", content=body, headers=upper))
replay = {**h, "X-GitHub-Delivery": "delivery-999"}
show("перехоплений, новий X-GitHub-Delivery", api.post("/github", content=body, headers=replay))
print("   оброблено подій:", processed["github"])

title("2. підпис від перезібраного JSON")
compact = b'{"action":"opened","number":7}'
show("підписано компактний JSON", api.post("/naive", content=compact, headers=github_headers(compact, "d")))
show("підписано json.dumps(...) з пробілами", api.post("/naive", content=body, headers=github_headers(body, "d")))
print("   json.dumps(json.loads(compact)) == compact:", json.dumps(json.loads(compact)).encode() == compact)

title("3. Stripe-стиль: час у підписі, id події")
event = json.dumps({"id": "evt_1", "type": "invoice.paid"}).encode()
print("   Stripe-Signature:", stripe_headers(event)["Stripe-Signature"][:26] + "…")
show("справжній", api.post("/stripe", content=event, headers=stripe_headers(event)))
show("повтор провайдера: новий t, новий підпис", api.post("/stripe", content=event,
                                                            headers=stripe_headers(event, int(time.time()) + 1)))
show("перехоплений годину тому", api.post("/stripe", content=event, headers=stripe_headers(event, int(time.time()) - 3600)))
old_v1 = stripe_headers(event, int(time.time()) - 3600)["Stripe-Signature"].split(",")[1]     # v1 годинної давності
show("старий v1, підставлено свіжий t", api.post("/stripe", content=event,
                                                  headers={"Stripe-Signature": f"t={int(time.time())},{old_v1}"}))
show("без t", api.post("/stripe", content=event, headers={"Stripe-Signature": "v1=abc"}))
print("   оброблено подій:", processed["stripe"])

title("4. ротація секрету: два v1 і два ключі на прийомі")
old, new = STRIPE_SECRETS[0], secrets.token_hex(32).encode()
e2 = json.dumps({"id": "evt_2", "type": "invoice.paid"}).encode()
e3 = json.dumps({"id": "evt_3", "type": "invoice.paid"}).encode()
STRIPE_SECRETS[:] = [new, old]                                          # приймач знає обидва
show("підписано старим (відправник ще не перейшов)", api.post("/stripe", content=e2, headers=stripe_headers(e2, keys=[old])))
show("підписано обома", api.post("/stripe", content=e3, headers=stripe_headers(e3, keys=[new, old])))
STRIPE_SECRETS[:] = [new]                                               # ротацію завершено
e4 = json.dumps({"id": "evt_4", "type": "invoice.paid"}).encode()
show("старим після завершення ротації", api.post("/stripe", content=e4, headers=stripe_headers(e4, keys=[old])))

title("5. Telegram: секретний заголовок")
show("правильний секрет", api.post("/telegram", json={"update_id": 1},
                                    headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_SECRET}))
show("без заголовка", api.post("/telegram", json={"update_id": 1}))
show("неправильний", api.post("/telegram", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "x"}))
