"""Сценарії пагінації на SQLite: зсув при вставці, глибокий offset проти курсора, білий список, вкладений ресурс."""
import base64
import json
import os
import time

os.environ.setdefault("DB_URL", "sqlite:///pagination_demo.db")
if os.path.exists("pagination_demo.db"):
    os.remove("pagination_demo.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import insert  # noqa: E402

from pagination_app import Base, Comment, Post, app, engine  # noqa: E402

N = 1_000_000
Base.metadata.create_all(engine)
with engine.begin() as conn:
    conn.execute(insert(Post), [{"title": f"Новина {i}", "category": ("news", "sport")[i % 2]}
                                for i in range(1, N + 1)])
    conn.execute(insert(Comment), [{"post_id": 1, "text": "до поста 1"}, {"post_id": 2, "text": "до поста 2"}])
c = TestClient(app)
ids = lambda items: [p["id"] for p in items]  # noqa: E731

print(f"Таблиця: {N:,} постів")
print("\n1. Новий пост між сторінками (новіші першими)")
p1 = c.get("/posts", params={"limit": 3}).json()
f1 = c.get("/posts/feed", params={"limit": 3}).json()
with engine.begin() as conn:
    conn.execute(insert(Post), [{"title": "Щойно опубліковано", "category": "news"}])
p2 = c.get("/posts", params={"offset": 3, "limit": 3}).json()
f2 = c.get("/posts/feed", params={"cursor": f1["next_cursor"], "limit": 3}).json()
print("  offset: сторінка 1", ids(p1), "→ сторінка 2", ids(p2))
print("  cursor: сторінка 1", ids(f1["items"]), "→ сторінка 2", ids(f2["items"]))

print("\n2. Глибока сторінка: та сама позиція, різні способи")
for label, params, url in [
    ("offset=0      ", {"offset": 0, "limit": 10}, "/posts"),
    ("offset=900000 ", {"offset": 900_000, "limit": 10}, "/posts"),
]:
    t = time.perf_counter(); r = c.get(url, params=params).json(); ms = (time.perf_counter() - t) * 1000
    print(f"  {label} {ms:7.1f} мс  перший id {r[0]['id']}")
cur = base64.urlsafe_b64encode(json.dumps({"id": r[0]["id"] + 1}).encode()).decode()
t = time.perf_counter(); r = c.get("/posts/feed", params={"cursor": cur, "limit": 10}).json()
print(f"  cursor        {(time.perf_counter() - t) * 1000:7.1f} мс  перший id {r['items'][0]['id']}")

print("\n3. Перевірки параметрів")
for params in [{"sort": "title; DROP TABLE posts"}, {"limit": 1000}]:
    r = c.get("/posts", params=params)
    print(f"  {params} → {r.status_code} {[e['msg'] for e in r.json()['detail']]}")
print("  cursor=сміття →", c.get("/posts/feed", params={"cursor": "сміття"}).status_code)

print("\n4. Вкладений ресурс")
for url in ["/posts/1/comments/1", "/posts/1/comments/2"]:
    r = c.get(url)
    print(f"  GET {url} → {r.status_code} {r.json()}")
