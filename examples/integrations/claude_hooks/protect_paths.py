"""PreToolUse-hook Claude Code: не дати інструментам Edit/Write змінити застосовані міграції й файли .env.

Підключення — у .claude/settings.json проєкту:

    "hooks": {"PreToolUse": [{"matcher": "Edit|Write",
              "hooks": [{"type": "command", "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/protect_paths.py\""}]}]}

Claude Code передає на stdin JSON події (tool_name, tool_input, cwd, hook_event_name, session_id …).
Код виходу 2 для PreToolUse — заблокувати виклик; stderr іде агентові як причина.
Це перевірка від випадкової правки, а не межа безпеки: `Bash(echo … > .env)` цей hook не бачить —
межа — permissions.deny і sandbox.
"""
import json
import sys
from pathlib import PurePosixPath

PROTECTED_DIRS = ("migrations/versions",)            # застосовану міграцію не редагують — пишуть нову
PROTECTED_NAMES = (".env",)


def reason(event: dict[str, object]) -> str | None:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = str(tool_input.get("file_path", "")).replace("\\", "/")
    cwd = str(event.get("cwd", "")).replace("\\", "/").rstrip("/")
    path = PurePosixPath(raw[len(cwd) + 1:] if cwd and raw.startswith(cwd + "/") else raw)
    if ".." in path.parts:
        return f"{raw}: шлях з '..' — працюй лише з файлами проєкту"
    if path.name in PROTECTED_NAMES or (path.name.startswith(".env.") and path.name != ".env.example"):
        return f"{raw}: секрети не редагуються агентом; приклад змінних — у .env.example"
    as_text = path.as_posix()
    for directory in PROTECTED_DIRS:
        if as_text.startswith(directory + "/") or f"/{directory}/" in as_text:
            return f"{raw}: застосовану міграцію не змінюють — створи нову: alembic revision --autogenerate"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("protect_paths: на stdin не JSON", file=sys.stderr)
        return 1                                     # не 2: зламаний hook не повинен блокувати все підряд
    if (why := reason(event)) is not None:
        print(why, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
