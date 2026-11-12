# Порядок і паралельність

> Крок 12 · розділ 3 з 4. Код: [`.github/workflows/news_hub.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/news_hub.yml) — `needs`, `strategy`, `timeout-minutes`.
> Теорія: [Частина X. Docker, Compose і CI/CD](../../10_docker_and_ci/README.md).

## Задача { #task }

Сім jobs, один з них — matrix на дві версії Python: вісім запусків. Якщо виконувати їх один за одним, PR чекатиме суму всіх тривалостей. Але й «усе одночасно» — погано:

- збирати образ і піднімати весь стек (найдовший job) немає сенсу, коли код уже не пройшов тести;
- публікувати образ можна лише тоді, коли пройшло **все**;
- упала одна версія Python — треба знати, що з другою, а не обірвати її на півдорозі;
- тест, що завис на мережі, не має тримати раннер годинами.

## Зміна: `needs` будує граф { #needs }

Jobs без `needs` стартують одночасно, кожен на своїй чистій машині. `needs` — «почни, коли ці jobs успішно завершились»:

```yaml title=".github/workflows/news_hub.yml (скорочено)"
jobs:
  tests:          # matrix: 3.10, 3.13 — needs немає
  min-versions:   # needs немає
  postgres:       # needs немає
  types:          # needs немає
  supply-chain:   # needs немає: lock, pip-audit, gitleaks

  docker:
    needs: tests                     # образ збираємо, лише коли код пройшов тести

  publish:
    needs: [tests, min-versions, postgres, types, supply-chain, docker]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```

- `docker` чекає лише `tests` — **обидва** варіанти matrix. Не чекає `min-versions`, `postgres`, `types`, `supply-chain`: це окремі обіцянки, а smoke — найдовший job, тож хай стартує якомога раніше.
- `publish` чекає всіх: образ у реєстр — лише з коміту, що пройшов усі перевірки, зокрема `supply-chain` ([розділ 2](what_to_check.md#supply-chain)): без відомих вразливостей у lock і без секретів в історії.

## Результат: хвилі { #waves }

Граф видно з самого файлу. Скрипт читає `jobs` і групує їх у хвилі: у першій — ті, що без `needs`, у кожній наступній — ті, чиї `needs` уже виконані.

```python title="waves.py"
import sys
import yaml

wf = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
jobs = wf["jobs"]
needs = {name: ([job["needs"]] if isinstance(job.get("needs"), str) else job.get("needs", [])) for name, job in jobs.items()}
done: set[str] = set()
wave = 1
while len(done) < len(jobs):
    ready = [n for n in jobs if n not in done and set(needs[n]) <= done]
    print(f"хвиля {wave}:", ", ".join(ready))
    done |= set(ready)
    wave += 1
for name, job in jobs.items():
    matrix = job.get("strategy", {}).get("matrix")
    if matrix:
        print(f"{name}: matrix {matrix} → {len(next(iter(matrix.values())))} запуски(в)")
    if "if" in job:
        print(f"{name}: if {job['if']}")
    if "permissions" in job:
        print(f"{name}: permissions {job['permissions']}")
print("workflow permissions:", wf["permissions"])
```

```text
$ python waves.py .github/workflows/news_hub.yml
хвиля 1: tests, min-versions, postgres, types, supply-chain
хвиля 2: docker
хвиля 3: publish
tests: matrix {'python': ['3.10', '3.13']} → 2 запуски(в)
publish: if github.event_name == 'push' && github.ref == 'refs/heads/main'
publish: permissions {'contents': 'read', 'packages': 'write'}
workflow permissions: {'contents': 'read'}
```

## Трасування: прогін на PR { #trace-pr }

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph T0 ["0. подія pull_request"]
        direction LR
        P0{"paths: змінено<br>steps/12_ci_cd/**?"} -- "так" --> Q0["news_hub — CI/CD"]
    end
    subgraph T1 ["хвиля 1: шість запусків паралельно"]
        direction LR
        A1["pytest 3.10"] ~~~ B1["pytest 3.13"] ~~~ C1["мін. версії"] ~~~ D1["mypy"] ~~~ E1["PostgreSQL<br>+ Redis"] ~~~ K1["lock, pip-audit,<br>gitleaks"]
    end
    subgraph T2 ["хвиля 2: needs tests (обидва з matrix)"]
        direction LR
        F2["образ + smoke"]
    end
    subgraph T3 ["хвиля 3: needs усі"]
        direction LR
        G3{"push у main?"} -- "ні" --> H3["publish:<br>skipped"]
    end
    T0 --> T1 --> T2 --> T3

    class P0,G3 decision
    class Q0 step
    class A1,B1,C1,D1,E1,K1,F2 success
    class H3 warning
```

На PR `publish` завжди `skipped`: умова `if` не виконується. Тривалість кожного job видно у вкладці **Actions** прогону; час усього прогону — це найдовший запуск хвилі 1 плюс `docker`, а не сума восьми.

## Трасування: упала одна версія Python { #trace-fail }

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph W1 ["хвиля 1"]
        direction LR
        A1["pytest 3.10:<br>failed"] ~~~ B1["pytest 3.13: доходить<br>до кінця (fail-fast: false)"] ~~~ C1["мін. версії, mypy,<br>PostgreSQL, supply-chain"]
    end
    subgraph W2 ["хвиля 2"]
        direction LR
        F2{"needs tests:<br>усі варіанти зелені?"} -- "ні" --> S2["docker:<br>skipped"]
    end
    subgraph W3 ["хвиля 3"]
        direction LR
        G3["publish:<br>skipped"]
    end
    W1 --> W2 --> W3

    class A1 error
    class B1,C1 success
    class F2 decision
    class S2,G3 warning
```

- **`needs` не виконано → job `skipped`**, а не «червоний»: у PR одна червона причина (`pytest · Python 3.10`), без лавини наслідків від образу й smoke.
- **`fail-fast: false`.** За замовчуванням (`fail-fast: true`) GitHub скасовує решту варіантів matrix, щойно один упав. Тоді не видно, чи проблема в одній версії Python, чи в обох. Коментар у файлі: «впала 3.10 — все одно дізнатися, що з 3.13».
- Інші jobs хвилі 1 від `tests` не залежать і доходять до кінця: за один прогін — усі незалежні причини.

## Ціна паралельності { #cost }

Кожен job — **окрема чиста машина**. Тому кроки повторюються: `actions/checkout`, `actions/setup-python`, `pip install -r requirements-dev.txt` — у `tests` (двічі), `postgres`, `types`, `docker`. Нічого з одного job в іншому немає, якщо не передати явно (артефакти, кеш).

Повтори здешевлює кеш pip:

```yaml
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python }}
          cache: pip
          cache-dependency-path: ${{ env.PROJECT }}/requirements*.txt
```

Ключ кешу — з вмісту `requirements.txt` і `requirements-dev.txt` кроку: змінив залежності — новий кеш, не змінив — `pip` бере вже завантажені пакети з кешу (`~/.cache/pip`), а не завантажує з PyPI заново. Встановлення в чисте середовище все одно відбувається в кожному job.

## `timeout-minutes` { #timeout }

| Job | `timeout-minutes` |
|---|---:|
| `tests`, `min-versions`, `postgres`, `publish` | 15 |
| `types`, `supply-chain` | 10 |
| `docker` | 20 |

Без `timeout-minutes` job може йти до шести годин — стільки дозволяє GitHub. Тест, що чекає на мережу без тайм-ауту, або `docker compose up --wait`, що не дочекався healthy, займали б раннер увесь цей час. Межа — з запасом над нормальною тривалістю; у `smoke.sh` своя, коротша: `--wait-timeout 180`.

## Правило { #rule }

!!! tip "Правило"
    Jobs — паралельно; `needs` — лише там, де справді треба чекати: дорогий job після дешевого, публікація — після всіх. `fail-fast: false` у matrix, щоб бачити всі варіанти. `timeout-minutes` на кожному job.

**Далі:** [Права, секрети, публікація](permissions_and_publish.md).
