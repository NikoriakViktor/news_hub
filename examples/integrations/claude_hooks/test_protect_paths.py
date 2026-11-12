"""Hook — звичайна програма: подаємо на stdin ту саму подію, яку надіслав би Claude Code, і дивимось код виходу.

    pytest -q claude_hooks
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).with_name("protect_paths.py")
CWD = "/home/you/news_hub"


def run(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, timeout=10)


def event(file_path: str, tool: str = "Edit") -> str:
    return json.dumps({"session_id": "s1", "hook_event_name": "PreToolUse", "cwd": CWD, "tool_name": tool,
                       "tool_input": {"file_path": file_path}})


@pytest.mark.parametrize("path", [f"{CWD}/news_hub/api.py", f"{CWD}/tests/unit/test_api.py",
                                  f"{CWD}/.env.example", f"{CWD}/docs/migrations/versions.md"])
def test_allowed(path: str) -> None:
    result = run(event(path))
    assert (result.returncode, result.stderr) == (0, "")


@pytest.mark.parametrize("path", [f"{CWD}/.env", f"{CWD}/.env.production",
                                  f"{CWD}/migrations/versions/0003_subscriptions.py", "migrations/versions/x.py",
                                  f"{CWD}/../other/secret.py"])
def test_blocked(path: str) -> None:
    result = run(event(path, tool="Write"))
    assert result.returncode == 2 and path in result.stderr


def test_env_example_is_not_a_secret() -> None:
    assert run(event(f"{CWD}/.env.example")).returncode == 0


def test_garbage_on_stdin_is_not_a_block() -> None:
    assert run("not json").returncode == 1
