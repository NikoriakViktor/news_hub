"""Спільний помічник демо: запустити uvicorn окремим процесом і дочекатися, поки він прийме з'єднання.

Сервер — окремий процес, а не потік у процесі клієнта: так клієнт і сервер не ділять GIL
і цикл подій, і виміри показують поведінку сервера, а не демо-скрипта.
"""
import contextlib
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

HERE = Path(__file__).parent


def running(app: str, port: int, *args: str, env: dict[str, str] | None = None, stderr=None):
    """`with running("blocking_app:app", 8762) as base:` → base = "http://127.0.0.1:8762"."""
    cmd = [sys.executable, "-m", "uvicorn", app, "--host", "127.0.0.1", "--port", str(port),
           "--log-level", "warning", *args]
    return running_cmd(cmd, port, env=env, stderr=stderr)


@contextlib.contextmanager
def running_cmd(cmd: list[str], port: int, env: dict[str, str] | None = None, stderr=None) -> Iterator[str]:
    """Будь-який сервер окремим процесом; чекаємо, поки порт прийме з'єднання. stderr — файл для журналу."""
    proc = subprocess.Popen(cmd, cwd=HERE, env={**os.environ, **(env or {})}, stderr=stderr)
    try:
        deadline = time.monotonic() + 15
        while True:
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
            if proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"{cmd[2:4]} не запустився на порту {port}")
            time.sleep(0.1)
        time.sleep(0.3)               # з --workers порт відкривається раніше, ніж готові всі процеси
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
