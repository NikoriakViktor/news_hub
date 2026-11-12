"""Локальне «джерело новин» для демо: повільні сторінки, збої і лічильник одночасних запитів.

    uvicorn upstream_app:app --port 8791

Заміняє справжні сайти: демо не ходять в інтернет, а затримки й збої — передбачувані.
"""
import asyncio

from fastapi import FastAPI, HTTPException

app = FastAPI()
state = {"in_flight": 0, "peak": 0, "served": 0}


@app.get("/page/{n}")
async def page(n: int, delay: float = 0.3) -> dict[str, int | str]:
    state["in_flight"] += 1
    state["peak"] = max(state["peak"], state["in_flight"])
    try:
        await asyncio.sleep(delay)
        state["served"] += 1
        return {"page": n, "title": f"Новина {n}"}
    finally:
        state["in_flight"] -= 1


@app.get("/fail/{n}")
async def fail(n: int, delay: float = 0.1) -> None:
    await asyncio.sleep(delay)
    raise HTTPException(503, f"сторінка {n} недоступна")


@app.get("/stats")
async def stats() -> dict[str, int]:
    return dict(state)


@app.post("/reset")
async def reset() -> dict[str, int]:
    state.update(in_flight=0, peak=0, served=0)
    return dict(state)
