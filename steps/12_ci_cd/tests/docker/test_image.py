"""Урок 48: образ news_hub перевіряємо так само, як код, — тестами. pytest -m docker

Збираємо образ з копії проєкту, куди навмисно підкладено те, що в образ потрапити не має права:
`.env` із «секретом», `.venv`, базу SQLite. Далі — справжні `docker run` / `docker stop`.
Без Docker (немає CLI чи демона) тести пропускаються.
"""
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
FAKE_SECRET = "JWT_SECRET=must-not-be-in-the-image-" + "x" * 32


def docker(*args: str, check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not docker_available(), reason="немає Docker")


@pytest.fixture(scope="module")
def image(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    context = tmp_path_factory.mktemp("context")
    shutil.copytree(PROJECT, context, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".venv", "__pycache__", ".mypy_cache", ".pytest_cache"))
    (context / ".env").write_text(FAKE_SECRET + "\n")                 # те, що лежить у кожного локально
    (context / ".venv").mkdir()
    (context / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    (context / "news_hub.db").write_bytes(b"SQLite format 3\x00")
    (context / "news_hub" / "__pycache__").mkdir(exist_ok=True)                 # кеш Python після тестів
    (context / "news_hub" / "__pycache__" / "api.cpython-313.pyc").write_bytes(b"\x00")
    tag = f"news_hub-test:{uuid.uuid4().hex[:8]}"
    docker("build", "-t", tag, str(context))
    yield tag
    docker("rmi", "-f", tag, check=False)


@pytest.fixture
def container(image: str) -> Iterator[str]:
    """Контейнер з частою перевіркою здоров'я (у Dockerfile — раз на 30 с)."""
    name = f"news-hub-test-{uuid.uuid4().hex[:8]}"
    docker("run", "-d", "--name", name, "--health-interval=1s", "--health-start-period=60s", image)
    yield name
    docker("rm", "-f", name, check=False)


def run(image: str, *command: str) -> subprocess.CompletedProcess[str]:
    return docker("run", "--rm", image, *command, check=False)


def test_local_files_are_not_in_the_image(image: str) -> None:
    listing = run(image, "ls", "-A", "/app").stdout.split()
    assert {".env", ".venv", "tests", "news_hub.db", "requirements-dev.txt"}.isdisjoint(listing), listing
    assert "must-not-be-in-the-image" not in docker("history", "--no-trunc", image).stdout
    caches = run(image, "find", "/app", "-name", "__pycache__", "-o", "-name", "*.pyc").stdout
    assert caches == "", caches                                        # і в підпапках, не лише в корені


def test_dev_dependencies_are_not_installed(image: str) -> None:
    for package in ("pytest", "mypy", "fakeredis"):
        assert run(image, "python", "-c", f"import {package}").returncode != 0, package


def test_runs_as_non_root_and_cannot_change_code(image: str) -> None:
    assert run(image, "id", "-u").stdout.strip() == "10001"
    assert run(image, "touch", "/app/news_hub/api.py").returncode != 0      # код належить root
    assert run(image, "touch", "/data/probe").returncode == 0               # том даних — користувачу app


def test_healthcheck_reports_healthy(container: str) -> None:
    deadline = time.monotonic() + 90
    status = ""
    while time.monotonic() < deadline:
        status = docker("inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{else}}no HEALTHCHECK{{end}}",
                        container).stdout.strip()
        if status in ("healthy", "unhealthy", "no HEALTHCHECK"):
            break
        time.sleep(1)
    assert status == "healthy", docker("logs", container, check=False).stderr[-2000:]


def test_docker_stop_is_graceful(container: str) -> None:
    test_healthcheck_reports_healthy(container)                              # застосунок уже запущений
    started = time.monotonic()
    docker("stop", "-t", "10", container)
    elapsed = time.monotonic() - started
    exit_code = docker("inspect", "-f", "{{.State.ExitCode}}", container).stdout.strip()
    logs = docker("logs", container).stderr
    assert exit_code == "0" and "Application shutdown complete" in logs, logs[-2000:]
    assert elapsed < 8, f"SIGTERM не дійшов до uvicorn: зупинка {elapsed:.1f} с (SIGKILL після 10 с)"


def test_migrations_run_on_a_volume(image: str) -> None:
    volume = f"news-hub-test-{uuid.uuid4().hex[:8]}"
    try:
        upgrade = docker("run", "--rm", "-v", f"{volume}:/data", image, "alembic", "upgrade", "head", check=False)
        assert upgrade.returncode == 0, upgrade.stderr
        current = docker("run", "--rm", "-v", f"{volume}:/data", image, "alembic", "current")
        assert "(head)" in current.stdout, current.stdout + current.stderr
    finally:
        docker("volume", "rm", "-f", volume, check=False)
