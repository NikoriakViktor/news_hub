"""PostToolUse-хук Claude Code: після кожної зміни .py-файлу проєкту — швидкі тести.

Claude Code передає на stdin JSON з полями tool_name і tool_input.file_path. Якщо тести впали,
код виходу 2: Claude бачить stderr (хвіст виводу pytest) і мусить виправити, перш ніж іти далі.
"""
import json
import subprocess
import sys

event = json.load(sys.stdin)
path = event.get("tool_input", {}).get("file_path", "")
if not path.endswith(".py"):
    sys.exit(0)

result = subprocess.run([sys.executable, "-m", "pytest", "-m", "unit", "-q", "-p", "no:cacheprovider", "-x"],
                        capture_output=True, text=True)
if result.returncode != 0:
    print("pytest -m unit впав після зміни", path, file=sys.stderr)
    print("\n".join(result.stdout.splitlines()[-25:]), file=sys.stderr)
    sys.exit(2)
