# Лаба 6. Укріплений образ Docker { #lab-06 }

| | |
|---|---|
| Основа | [крок 10](../tutorials/10_docker/index.md) — `steps/10_docker` |
| Що тренує | багатоетапна збірка, права файлів в образі, setuid, мітки OCI, `--read-only`; тести образу з `pytest -m docker` |
| Складність | ★★☆ |
| Орієнтовний час | 2–3 години (збірка образу — хвилина-дві на кожен прогін) |

## Мета { #goal }

**Задача.** Образ кроку 10 уже не містить `.env` і тестів, працює не від root, і користувач `app` не може змінити код.
Але уяви, що хтось знайшов у застосунку дірку й виконує команди в контейнері від імені `app`. Що він там знайде?

- `pip` — можна доставити будь-який пакет з інтернету просто в контейнері;
- 11 програм з бітом setuid або setgid (`su`, `passwd`, `mount`, …): вони запускаються з правами root чи групи `shadow`, і помилка в будь-якій
  з них — шлях до root;
- якщо образ зібрано з робочої копії на NTFS (WSL, `/mnt/c/...`), усі файли мають права `rwxrwxrwx`, тож
  `app` **може** переписати код. Тест кроку 10 `test_runs_as_non_root_and_cannot_change_code` у такій копії червоний;
- немає жодної мітки, з якої видно, з якого репозиторію і якої версії цей образ.

**Зміна.** Багатоетапна збірка без `pip` у фінальному образі, прибрані біти setuid/setgid, права коду задано під
час `COPY`, мітки OCI з версією як аргументом збірки.

**Результат.** Новий файл тестів образу `tests/docker/test_hardening.py` (5 тестів) і всі тести кроку 10 зелені.

**Правило.** В образі для продакшну — лише те, що потрібно для **запуску**. Інструменти встановлення й підвищення прав
належать стадії збірки, а права коду не повинні залежати від того, на якій машині образ збирали.

## Звідки починаємо { #start }

```bash
cp -r steps/10_docker lab_06 && cd lab_06
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

```text
360 passed, 8 deselected
```

Потрібен Docker: тести цієї лаби — `pytest -m docker`, вони збирають і запускають справжній образ.

Перед роботою подивись, що вже є в образі кроку 10 (`docker build -t news_hub:10 .`):

```text
$ docker run --rm news_hub:10 pip --version
pip 25.0.1 from /usr/local/lib/python3.12/site-packages/pip (python 3.12)
```

## Вимоги { #requirements }

1. **Без інсталятора пакетів.** У фінальному образі `python -m pip` завершується помилкою, а `pip` і `pip3` відсутні
   в `PATH`. Залежності встановлюються на окремій стадії збірки.
2. **Без setuid/setgid.** `find / -xdev -type f -perm /6000` в образі нічого не знаходить.
3. **Код лише для читання за будь-яких прав на машині збірки.** Ніхто, крім власника root, не може писати в `/app`
   (`find /app -perm /022` порожній), навіть якщо в робочій копії всі файли мають права `777`.
4. **Мітки OCI:** `org.opencontainers.image.title=news_hub`,
   `org.opencontainers.image.source=https://github.com/NikoriakViktor/news_hub`,
   `org.opencontainers.image.version` — з аргументу збірки `APP_VERSION` (за замовчуванням `dev`).
5. **Працює з `--read-only`:** міграції й сервер запускаються з кореневою файловою системою лише для читання,
   з томом `/data` і `--tmpfs /tmp`.
6. Усе з кроку 10 лишається: користувач `10001`, `HEALTHCHECK`, коректна зупинка, `alembic upgrade head` на томі.
   `tests/docker/test_image.py` не змінюємо.

## Критерії приймання { #acceptance }

Поклади файл у `tests/docker/test_hardening.py`. Він бере `docker()`, `docker_available()` і `PROJECT` з
`tests/docker/test_image.py` і збирає образ з копії проєкту, де всі файли мають права `777`, тобто так, як їх бачить Linux
на NTFS.

```python title="tests/docker/test_hardening.py"
"""Лаба 6: образ, у якому зламаному процесу нема чим скористатися. pytest -m docker tests/docker/test_hardening.py"""
import json
import shutil
import time
import uuid
from collections.abc import Iterator

import pytest

from tests.docker.test_image import PROJECT, docker, docker_available

pytestmark = pytest.mark.skipif(not docker_available(), reason="немає Docker")

VERSION = "9.9.9-lab"


@pytest.fixture(scope="module")
def image(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Збірка з копії, де всі файли rwxrwxrwx — так їх бачить Linux у робочій копії на NTFS (WSL, /mnt/c)."""
    context = tmp_path_factory.mktemp("context")
    shutil.copytree(PROJECT, context, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".venv", "__pycache__", ".mypy_cache", ".pytest_cache"))
    for path in [context, *context.rglob("*")]:
        path.chmod(0o777)
    tag = f"news_hub-hardening:{uuid.uuid4().hex[:8]}"
    docker("build", "--build-arg", f"APP_VERSION={VERSION}", "-t", tag, str(context))
    yield tag
    docker("rmi", "-f", tag, check=False)


def run(image: str, *command: str, user: str = "") -> tuple[int, str]:
    as_user = ["--user", user] if user else []
    result = docker("run", "--rm", *as_user, image, *command, check=False)
    return result.returncode, (result.stdout + result.stderr).strip()


def test_no_package_installer_in_the_image(image: str) -> None:
    code, output = run(image, "python", "-m", "pip", "--version")
    assert code != 0, f"pip є в образі: {output}"
    code, output = run(image, "sh", "-c", "command -v pip pip3 || true")
    assert output == "", f"pip на PATH: {output}"


def test_no_setuid_or_setgid_binaries(image: str) -> None:
    # root — щоб find бачив усі папки; перевіряємо права файлів, а не те, під ким працює застосунок
    code, output = run(image, "find", "/", "-xdev", "-type", "f", "-perm", "/6000", user="0")
    assert code == 0 and output == "", f"файли з setuid/setgid:\n{output}"


def test_code_is_read_only_whatever_the_host_permissions(image: str) -> None:
    code, output = run(image, "find", "/app", "-perm", "/022")
    assert code == 0 and output == "", f"група чи всі можуть писати:\n{output[:500]}"
    code, _ = run(image, "touch", "/app/news_hub/api.py")
    assert code != 0, "користувач app змінив код"


def test_oci_labels(image: str) -> None:
    labels = json.loads(docker("image", "inspect", "-f", "{{json .Config.Labels}}", image).stdout) or {}
    assert labels.get("org.opencontainers.image.title") == "news_hub", labels
    assert labels.get("org.opencontainers.image.source") == "https://github.com/NikoriakViktor/news_hub", labels
    assert labels.get("org.opencontainers.image.version") == VERSION, labels


def test_app_still_works_on_a_read_only_root(image: str) -> None:
    name, volume = f"news-hub-ro-{uuid.uuid4().hex[:8]}", f"news-hub-ro-{uuid.uuid4().hex[:8]}"
    try:
        migrate = docker("run", "--rm", "--read-only", "-v", f"{volume}:/data", image,
                         "alembic", "upgrade", "head", check=False)
        assert migrate.returncode == 0, migrate.stderr[-2000:]
        docker("run", "-d", "--name", name, "--read-only", "--tmpfs", "/tmp", "-v", f"{volume}:/data",
               "--health-interval=1s", image)
        status, deadline = "", time.monotonic() + 60
        while time.monotonic() < deadline and status not in ("healthy", "unhealthy"):
            time.sleep(1)
            status = docker("inspect", "-f", "{{.State.Health.Status}}", name).stdout.strip()
        assert status == "healthy", docker("logs", name, check=False).stderr[-2000:]
    finally:
        docker("rm", "-f", name, check=False)
        docker("volume", "rm", "-f", volume, check=False)
```

**До змін** (Dockerfile кроку 10), `pytest -m docker tests/docker/test_hardening.py -q`, скорочено:

```text
E       AssertionError: pip є в образі: pip 25.0.1 from /usr/local/lib/python3.12/site-packages/pip (python 3.12)
E       AssertionError: файли з setuid/setgid:
E         /usr/sbin/unix_chkpwd
E         /usr/bin/mount
E         /usr/bin/chage
E         /usr/bin/chfn
E         /usr/bin/chsh
E         /usr/bin/expiry
E         /usr/bin/gpasswd
E         /usr/bin/su
E         /usr/bin/passwd
E         /usr/bin/umount
E         /usr/bin/newgrp
E       AssertionError: група чи всі можуть писати:
E         /app/data
E         /app/data/rbc_news_snapshot.json
E         /app/migrations
E         ...
E       AssertionError: {}
FAILED tests/docker/test_hardening.py::test_no_package_installer_in_the_image
FAILED tests/docker/test_hardening.py::test_no_setuid_or_setgid_binaries - As...
FAILED tests/docker/test_hardening.py::test_code_is_read_only_whatever_the_host_permissions
FAILED tests/docker/test_hardening.py::test_oci_labels - AssertionError: {}
4 failed, 1 passed in 19.82s
```

`test_app_still_works_on_a_read_only_root` зелений з самого початку: `PYTHONDONTWRITEBYTECODE=1` і база на томі
`/data` з кроку 10 уже прибрали всі записи поза томом. Цей тест — **запобіжник**: він не дасть зламати це під час
змін у цій лабі.

**Після змін** — усі тести образу, і кроку 10, і нові:

```text
$ pytest -m docker -q
...........                                                              [100%]
11 passed, 362 deselected in 70.42s
$ pytest -q
360 passed, 13 deselected
```

## Підказки { #hints }

??? tip "Чому не просто `RUN pip uninstall pip` в кінці?"
    Можна, і `pip` зникне. Але тоді залежності встановлюються в тому самому образі, де потім працює застосунок, і
    все, що знадобилось для збірки (кеші, компілятори, якщо колись з'являться пакети без готових wheel), залишиться
    в шарах. Окрема стадія `builder` з `python -m venv /opt/venv` збирає залежності, а фінальна стадія копіює
    готовий `/opt/venv`. `pip` всередині venv теж можна видалити: `/opt/venv/bin/pip uninstall -y pip`.

??? tip "Де шукати setuid і чому `--user 0` у тесті"
    `find / -xdev -type f -perm /6000` — файли з бітом setuid (4000) або setgid (2000); `-xdev` не заходить у `/proc`
    і змонтовані томи. Від імені `app` `find` не бачить `/root` та інших закритих папок і повертає код 1, тому тест
    запускає саме `find` від root. Застосунок при цьому так і працює від `10001`. Біт знімає `chmod a-s`.

??? tip "Права файлів, які приходять з машини збірки"
    `COPY` переносить права файлів з контексту як є. На NTFS через WSL Linux бачить `777`. Без BuildKit тут
    знадобився б окремий `RUN chmod -R go-w /app`, а це ще один шар з копією всього коду. `COPY --chmod=...`
    задає права одразу. Символьний запис `u=rwX,go=rX` дає каталогам `755`, а файлам без біта виконання `644`.

??? tip "Мітка з версією і кеш шарів"
    `ARG APP_VERSION` + `LABEL ...version="${APP_VERSION}"` поблизу `FROM` змусять перезбирати всі наступні шари при
    кожній новій версії. Постав їх **в кінці** Dockerfile: тоді зміна версії оновлює лише метадані.

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"

    ```dockerfile title="Dockerfile (лаба 6, основні зміни)"
    # --- стадія 1: збірка залежностей. pip потрібен лише тут, у фінальний образ він не йде.
    FROM python:3.12-slim AS builder
    ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
        PIP_ROOT_USER_ACTION=ignore
    RUN python -m venv /opt/venv
    COPY requirements.txt .
    RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
        && /opt/venv/bin/pip uninstall -y pip

    # --- стадія 2: те, що запускається.
    FROM python:3.12-slim

    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PATH=/opt/venv/bin:$PATH

    # Без інсталятора пакетів і без setuid/setgid: зламаному процесу нічого доставити й нікуди підвищити права.
    RUN python -m pip uninstall -y pip \
        && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
        && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
        && mkdir /data && chown app /data

    COPY --from=builder /opt/venv /opt/venv

    WORKDIR /app
    # --chmod: код лише для читання, хоч би які права були у файлів на машині збірки (NTFS/WSL дає 777)
    COPY --chmod=u=rwX,go=rX . .

    USER app
    ENV DATABASE_URL=sqlite+aiosqlite:////data/news_hub.db
    EXPOSE 8000

    HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
        CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

    # Мітки — останніми: зміна версії не інвалідує шари із залежностями й кодом.
    ARG APP_VERSION=dev
    LABEL org.opencontainers.image.title="news_hub" \
          org.opencontainers.image.source="https://github.com/NikoriakViktor/news_hub" \
          org.opencontainers.image.version="${APP_VERSION}"

    CMD ["uvicorn", "news_hub.api:app", "--host", "0.0.0.0", "--port", "8000"]
    ```

    Що варто помітити:

    - `PATH=/opt/venv/bin:$PATH`: `python`, `uvicorn` і `alembic` беруться з venv. `HEALTHCHECK` і `CMD` не змінились;
    - venv збирається на тому самому `python:3.12-slim`, що й фінальна стадія. Посилання `/opt/venv/bin/python` веде
      на `/usr/local/bin/python`, і в обох стадіях там той самий інтерпретатор;
    - розмір образу майже не змінився (440 → 441 МБ у `docker image ls`): мета цієї лаби — менше можливостей
      для атакувальника, а не менший образ.

    Перевірка руками:

    ```bash
    docker build --build-arg APP_VERSION=1.0.0 -t news_hub:hard .
    docker run --rm news_hub:hard sh -c 'ls -la /app/news_hub/api.py; which python uvicorn'
    docker image inspect news_hub:hard -f '{{json .Config.Labels}}'
    ```

## Що перевірити самому { #self-check }

- [ ] `pytest -m docker -q` зелений: і нові тести, і `tests/docker/test_image.py` кроку 10.
- [ ] Можеш пояснити, чому тест кроку 10 «код не можна змінити» червоний, якщо образ зібрано з `/mnt/c/...`, і
      чому `COPY --chmod` виправляє це без додаткового шару.
- [ ] Знаєш, що робить біт setuid і чому `passwd` з ним — ризик у контейнері, де нікому не треба змінювати пароль.
- [ ] Можеш пояснити, чому `ARG`/`LABEL` з версією стоять у кінці Dockerfile.
- [ ] Перевірив руками: `docker run --read-only --tmpfs /tmp -v news_data:/data news_hub:hard` стає `healthy`.
      Тепер прибери `--tmpfs /tmp` і подивись, чи щось зламається. Якщо ні — поясни, чому `/tmp` усе одно
      варто давати.
- [ ] Подумай, що ще можна прибрати з образу (оболонку `sh`, `apt`) і що тоді перестане працювати
      (`docker exec ... sh`, `command -v` у тестах).
