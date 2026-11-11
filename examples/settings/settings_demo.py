"""pydantic-settings: звідки беруться значення, SecretStr, .env, типові пастки.

    pip install -r requirements.txt
    python settings_demo.py
"""
import json
import os
import tempfile
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

os.environ["DEMO_NAME"] = "olena"
work = Path(tempfile.mkdtemp())
(work / ".env").write_text(
    "APP_ENVIRONMENT=from-dotenv\n"
    "APP_DATABASE_URL=postgresql://news:dotenv-pass@db/news\n"
    "APP_JWT_SECRET=dotenv-secret-0123456789abcdef0123456789\n"
    "APP_ADMIN_HASH='$2b$12$abcdefghijklmnopqrstuv'\n"
    "APP_ADMIN_HASH_UNQUOTED=$2b$12$abcdefghijklmnopqrstuv\n"
    "APP_GREETING='hello-${DEMO_NAME}'\n"
    "DOCKER_PORT=8080\n",
    encoding="utf-8",
)
secrets = work / "secrets"
secrets.mkdir()
(secrets / "app_environment").write_text("from-secrets-dir")


class Strict(BaseSettings):                          # extra за замовчуванням — "forbid"
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=work / ".env", secrets_dir=secrets)
    database_url: str
    jwt_secret: SecretStr
    environment: str = ""
    admin_hash: str = ""
    admin_hash_unquoted: str = ""
    greeting: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=work / ".env", secrets_dir=secrets,
                                      extra="ignore")

    environment: str = "from-default"
    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    admin_hash: str = ""
    admin_hash_unquoted: str = ""
    greeting: str = ""
    workers: int = 1


def show(title: str, factory) -> None:
    try:
        print(f"   {title:44} {factory()}")
    except ValidationError as exc:
        print(f"   {title:44} ValidationError: {exc.errors()[0]['type']} {exc.errors()[0]['loc']}")
        print(f"   {'':44} str(exc) містить: {str(exc).splitlines()[2].strip()[:110]}")


print("--- 0. чужий ключ у .env (DOCKER_PORT)")
show("extra за замовчуванням", Strict)
show('dotenv_filtering="match_prefix" (≥ 2.14)',
     lambda: type("Filtered", (Strict,), {"model_config": {**Strict.model_config, "dotenv_filtering": "match_prefix"}})().database_url)

print("--- 1. пріоритет джерел для environment")
show("default ← secrets_dir ← .env", lambda: Settings().environment)
os.environ["APP_ENVIRONMENT"] = "from-os-environ"
show("+ змінна середовища", lambda: Settings().environment)
show("+ аргумент Settings(environment=...)", lambda: Settings(environment="from-init").environment)
del os.environ["APP_ENVIRONMENT"]
(work / ".env").write_text((work / ".env").read_text().replace("APP_ENVIRONMENT=from-dotenv\n", ""))
show("без .env-рядка: secrets_dir", lambda: Settings().environment)

print("--- 2. SecretStr")
settings = Settings()
print("   repr:", repr(settings.jwt_secret), "| str:", str(settings.jwt_secret), "| f-рядок:", f"{settings.jwt_secret}")
print("   get_secret_value():", settings.jwt_secret.get_secret_value()[:12] + "…")
print("   print(settings):", str(settings)[:130], "…")
print("   model_dump():", settings.model_dump()["jwt_secret"].__class__.__name__,
      "| model_dump(mode='json'):", settings.model_dump(mode="json")["jwt_secret"])
print("   database_url (str) у print(settings):", "dotenv-pass" in str(settings))
print("   JSON Schema:", json.dumps(Settings.model_json_schema()["properties"]["jwt_secret"]))

print("--- 3. $ у .env")
print("   у лапках:", settings.admin_hash, "| без лапок:", settings.admin_hash_unquoted)
print("   ${DEMO_NAME} в одинарних лапках:", settings.greeting)

print("--- 4. помилки при старті")
os.environ["APP_JWT_SECRET"] = "short-secret"
show("APP_JWT_SECRET закороткий (SecretStr)", Settings)
del os.environ["APP_JWT_SECRET"]
os.environ["APP_WORKERS"] = "four"
show("APP_WORKERS=four", Settings)
del os.environ["APP_WORKERS"]


class FromOtherDir(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")
    database_url: str = "default-not-from-env"


os.chdir(tempfile.gettempdir())
show("env_file='.env', запуск з іншої папки", lambda: FromOtherDir().database_url)
os.environ["app_database_url"] = "lowercase-name"
show("змінна в нижньому регістрі", lambda: FromOtherDir().database_url)
del os.environ["app_database_url"]

print("--- 5. один екземпляр на процес")
first, second = Settings.settings_cached(), Settings.settings_cached()      # pydantic-settings ≥ 2.16
print("   settings_cached() двічі — той самий об'єкт:", first is second)
Settings.settings_clear_cache()
print("   після settings_clear_cache():", Settings.settings_cached() is first)
try:
    from pydantic import BaseSettings as OldBaseSettings  # noqa: F401
except Exception as exc:
    print("   from pydantic import BaseSettings:", type(exc).__name__, str(exc).splitlines()[0][:90])
