"""Згенерувати .env для CI чи першого запуску: випадкові пароль бази й JWT_SECRET, хеш пароля адміна. Урок 50.

    python scripts/make_env.py                      # пароль адміна — випадковий, друкується один раз
    ADMIN_PASSWORD=… python scripts/make_env.py      # свій пароль адміна (CI: зі змінної, не з коду)

Існуючий .env не перезаписує. Значення з `$` (bcrypt-хеш) — в одинарних лапках: так їх читає Compose (урок 49).
"""
import os
import secrets
import sys
from pathlib import Path

import bcrypt

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    target = ROOT / ".env"
    if target.exists():
        print(f"{target} уже є — не чіпаю", file=sys.stderr)
        return 1
    password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(16)
    values = {
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
        "ADMIN_PASSWORD_HASH": bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode(),
        "JWT_SECRET": secrets.token_urlsafe(48),
        "HTTP_PORT": os.environ.get("HTTP_PORT", "80"),
    }
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        lines.append(f"{key}='{values.pop(key)}'" if key in values and not line.startswith("#") else line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(0o600)
    if "ADMIN_PASSWORD" not in os.environ:
        print(f"пароль адміна: {password}")
    print(f"створено {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
