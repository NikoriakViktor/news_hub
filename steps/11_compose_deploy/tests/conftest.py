"""Спільне для всіх тестів: HTML-фікстури і маркери за папкою (фабрики даних — tests/factories.py).

tests/unit/         — швидкі: одна функція чи клас, без бази, Redis і мережі   → pytest -m unit
tests/integration/  — API разом з базою й Redis (SQLite/fakeredis або справжні) → pytest -m integration
tests/docker/       — образ Docker: збірка, користувач, healthcheck, зупинка     → pytest -m docker (урок 48)
"""
from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Маркер з назви папки: не треба пам'ятати про @pytest.mark.unit у кожному файлі."""
    for item in items:
        for layer in ("unit", "integration", "docker"):
            if f"{Path('tests') / layer}" in str(item.path):
                item.add_marker(getattr(pytest.mark, layer))


@pytest.fixture
def html() -> Callable[[str], str]:
    """html("demo_newsline") → вміст tests/fixtures/demo_newsline.html."""
    return lambda name: (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
