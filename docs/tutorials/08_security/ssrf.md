# SSRF: куди ходить сервер

> Крок 8 · розділ 2 з 4. Код: [`news_hub/safe_fetch.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/news_hub/safe_fetch.py), [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/news_hub/api.py), [`migrations/versions/0003_sources_table.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/migrations/versions/0003_sources_table.py).
> Теорія: [Частина VIII. Безпека API](../../08_security/README.md).

## Задача { #task }

Нова можливість: адмін додає RSS-джерело за адресою (`POST /api/sources`), сервер завантажує стрічку (`POST /api/sources/{id}/fetch`) і пропускає її через той самий `parse_pravda_rss` → `NewsItem` → база. Джерела лежать у новій таблиці `sources` (міграція `0003`, унікальний `url`).

Тут і з'являється **SSRF** (Server-Side Request Forgery, OWASP Top 10, A10). Атакувальник не може дістатися внутрішньої мережі сам, але може **попросити сервер**. Що ховається за «внутрішніми» адресами:

| Адреса | Що там буває |
|---|---|
| `127.0.0.1`, `localhost`, `[::1]` | сам сервер: Redis без пароля, адмінки, debug-панелі |
| `10.x`, `172.16–31.x`, `192.168.x` | інші сервіси компанії |
| `169.254.169.254` | **метадані хмари** (AWS, GCP, Azure): тимчасові ключі доступу до всього акаунта |
| `0.0.0.0`, `100.64.x` | «цей хост», мережа провайдера (CGNAT) |

Задача: сервер завантажує **будь-яку** публічну RSS-стрічку і **жодної** внутрішньої адреси — хоч напряму, хоч через перенаправлення.

## Старий захист: перевірити рядок { #old }

Типовий захист з прикладів OWASP A10 — список дозволених хостів:

```python title="приклад з OWASP Top 10, A10 (стартовий код)"
ALLOWED_HOSTS_FOR_FETCH = ['i.imgur.com', 'avatars.githubusercontent.com']

def is_safe_url(url):
    parsed = urlparse(url)
    return parsed.hostname in ALLOWED_HOSTS_FOR_FETCH

def upload_avatar(request):
    url = request.POST.get('avatar_url')
    if not is_safe_url(url):
        raise PermissionDenied
    response = requests.get(url)
```

Перевірено **рядок** URL, а з'єднання йде туди, куди скаже мережа. Хто керує дозволеним сайтом (чи знайшов у ньому «відкрите перенаправлення»), відповідає `302` на внутрішню адресу, а `requests.get` іде за перенаправленням сам. Два локальні сервери: «дозволений» (у цій демонстрації — `127.0.0.1`, він у `ALLOWED_HOSTS_FOR_FETCH`) відповідає `302` на «внутрішній» `localhost:<порт>/latest/meta-data/`:

```text
is_safe_url: True
фінальна адреса: http://localhost:40349/latest/meta-data/
відповідь: INTERNAL: aws_secret_access_key=...
```

Для нашого випадку allowlist ще й не підходить: адмін має додавати будь-яке RSS, а не три наперед відомі сайти.

## Зміна 1: перевірки без DNS — `check_url` { #check-url }

`safe_fetch` перевіряє не рядок, а **адресу, куди йде з'єднання**. Почнемо з того, що видно в самому URL:

```python title="news_hub/safe_fetch.py"
def check_url(url: str | URL, policy: FetchPolicy = DEFAULT_POLICY) -> URL:
    """Перевірки, для яких не потрібен DNS. Повертає розібраний URL."""
    parsed = URL(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL(f"схема {parsed.scheme or '(немає)'}: дозволено лише http і https")
    if not parsed.host:
        raise UnsafeURL("в адресі немає хоста")
    if parsed.user or parsed.password:
        raise UnsafeURL("логін і пароль в адресі не дозволено")
    if parsed.port not in policy.allowed_ports:
        raise UnsafeURL(f"порт {parsed.port}: дозволено {sorted(policy.allowed_ports)}")
    try:
        literal = ipaddress.ip_address(parsed.host)
    except ValueError:
        return parsed                    # ім'я хоста — перевірить resolver після DNS
    check_ip(str(literal), policy)       # IP в адресі aiohttp не резолвить — перевіряємо тут
    return parsed
```

Яка IP «публічна» — вирішує стандартний модуль `ipaddress`:

```python title="news_hub/safe_fetch.py"
def normalize(ip: IPAddress) -> IPAddress:
    """::ffff:127.0.0.1 — це 127.0.0.1: перевіряємо IPv4 всередині IPv6."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def is_public_ip(ip: IPAddress) -> bool:
    """is_global: не приватна, не loopback, не link-local, не 0.0.0.0, не зарезервована, не 100.64/10."""
    ip = normalize(ip)
    return ip.is_global and not ip.is_multicast


@dataclass(frozen=True)
class FetchPolicy:
    """Що дозволено. За замовчуванням — лише публічний інтернет; тести звужують чи розширюють явно."""
    allow_ip: Callable[[IPAddress], bool] = is_public_ip
    allowed_ports: frozenset[int] = frozenset({80, 443})
    max_redirects: int = 3
    max_bytes: int = 2_000_000
    timeout: float = 10.0
    content_types: tuple[str, ...] = FEED_CONTENT_TYPES
```

Результат на різних адресах:

```text
file:///etc/passwd                            → UnsafeURL: схема file: дозволено лише http і https
gopher://example.com/                         → UnsafeURL: схема gopher: дозволено лише http і https
http://example.com:6379/                      → UnsafeURL: порт 6379: дозволено [80, 443]
http://example.com:22/                        → UnsafeURL: порт 22: дозволено [80, 443]
https://user:pass@example.com/                → UnsafeURL: логін і пароль в адресі не дозволено
http://127.0.0.1/                             → UnsafeURL: адреса 127.0.0.1 — loopback: сервер туди не звертається
http://[::1]/                                 → UnsafeURL: адреса ::1 — loopback: сервер туди не звертається
http://[::ffff:127.0.0.1]/                    → UnsafeURL: адреса 127.0.0.1 — loopback: сервер туди не звертається
http://169.254.169.254/latest/meta-data/      → UnsafeURL: адреса 169.254.169.254 — link-local: сервер туди не звертається
http://10.0.0.5/                              → UnsafeURL: адреса 10.0.0.5 — приватна мережа: сервер туди не звертається
http://192.168.1.1/                           → UnsafeURL: адреса 192.168.1.1 — приватна мережа: сервер туди не звертається
http://0.0.0.0/                               → UnsafeURL: адреса 0.0.0.0 — 0.0.0.0 — «цей хост»: сервер туди не звертається
http://100.64.0.1/                            → UnsafeURL: адреса 100.64.0.1 — не публічна: сервер туди не звертається
http://2130706433/                            → пройшов, host=2130706433
http://0x7f.1/                                → пройшов, host=0x7f.1
http://127.1/                                 → пройшов, host=127.1
http://localhost/admin                        → пройшов, host=localhost
https://www.pravda.com.ua/rss/view_news/      → пройшов, host=www.pravda.com.ua
```

Останні п'ять пройшли: для `ipaddress` це не IP-адреси, а **імена**. Але `2130706433` (десятковий запис), `0x7f.1` (шістнадцятковий), `127.1` (скорочений) і `localhost` — це все `127.0.0.1`. Ім'я без DNS не перевірити, тож далі працює resolver.

## Зміна 2: IP після DNS — `PolicyResolver` { #resolver }

```python title="news_hub/safe_fetch.py"
class PolicyResolver(ThreadedResolver):
    """DNS + перевірка: aiohttp під'єднується лише до адрес, які повернув цей resolver."""

    def __init__(self, policy: FetchPolicy) -> None:
        super().__init__()
        self._policy = policy

    async def resolve(self, host: str, port: int = 0,
                      family: socket.AddressFamily = socket.AF_INET) -> list[ResolveResult]:
        results = await super().resolve(host, port, family)
        for result in results:           # «2130706433», «0x7f.1», «localhost» — getaddrinfo дає 127.0.0.1
            check_ip(result["host"], self._policy)
        return results
```

Ті самі імена через resolver (лише `getaddrinfo`, без з'єднання):

```text
localhost       → UnsafeURL: адреса 127.0.0.1 — loopback: сервер туди не звертається
2130706433      → UnsafeURL: адреса 127.0.0.1 — loopback: сервер туди не звертається
0x7f.1          → UnsafeURL: адреса 127.0.0.1 — loopback: сервер туди не звертається
127.1           → UnsafeURL: адреса 127.0.0.1 — loopback: сервер туди не звертається
017700000001    → UnsafeURL: адреса 127.0.0.1 — loopback: сервер туди не звертається
```

Якщо DNS поверне **кілька** адрес, перевіряється кожна: одна внутрішня серед публічних — уже відмова.

**Чому перевірка саме в resolver, а не окремо перед запитом.** Якщо спершу запитати DNS «чи публічна адреса?», а потім з'єднатися, DNS-сервер атакувальника може відповісти двічі по-різному: перший раз — публічна IP, другий — `127.0.0.1`. Це **DNS rebinding**. Resolver з'єднання повертає aiohttp саме ті адреси, які перевірив, а `use_dns_cache=False` не дає взяти стару відповідь з кешу. Між перевіркою і з'єднанням нічого не змінюється.

**Чому `check_url` перевіряє IP-літерал сам.** Для `http://169.254.169.254/` aiohttp **не викликає** resolver: адреса вже є. Тому IP в URL перевіряється одразу, без DNS.

## Зміна 3: кожне перенаправлення — знову через перевірки { #redirects }

```python title="news_hub/safe_fetch.py"
async def safe_fetch(url: str, policy: FetchPolicy = DEFAULT_POLICY) -> FetchResult:
    """GET чужої адреси з усіма перевірками. UnsafeURL — адреса заборонена; FetchError — не вдалося."""
    current = check_url(url, policy)
    chain = [str(current)]
    connector = aiohttp.TCPConnector(resolver=PolicyResolver(policy), use_dns_cache=False)
    timeout = aiohttp.ClientTimeout(total=policy.timeout)
    # trust_env=False: без HTTP_PROXY з середовища — інакше з'єднання йшло б через проксі, повз наш resolver
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
        for redirects in range(policy.max_redirects + 1):
            try:
                async with session.get(current, headers=HEADERS, allow_redirects=False) as resp:
                    if resp.status in REDIRECT_STATUSES:
                        location = resp.headers.get("Location")
                        if not location:
                            raise FetchError(f"HTTP {resp.status} без Location")
                        current = check_url(current.join(URL(location)), policy)
                        chain.append(str(current))
                        continue
                    if resp.status != 200:
                        raise FetchError(f"HTTP {resp.status}")
                    if resp.content_type not in policy.content_types:
                        raise FetchError(f"тип вмісту {resp.content_type}: очікуємо RSS/XML")
                    body = await _read_limited(resp, policy.max_bytes)
                    return FetchResult(url=str(current), content_type=resp.content_type, body=body,
                                       redirects=redirects, charset=resp.charset, chain=chain)
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:   # у 3.10 це ще не TimeoutError
                raise FetchError(f"{type(error).__name__}: {error}") from error
    raise FetchError(f"більше {policy.max_redirects} перенаправлень")
```

Усі перевірки разом:

| Перевірка | Навіщо |
|---|---|
| схема лише `http`/`https` | `file:///etc/passwd`, `gopher://` — інші протоколи |
| порт лише 80/443 | `http://example.com:6379/` — Redis, `:22` — SSH |
| без `user:pass@` в URL | облікові дані чужого сервісу в нашому запиті |
| IP-літерал в адресі — перевірити одразу | для `http://169.254.169.254/` aiohttp **не викликає** resolver |
| ім'я → IP через `PolicyResolver`, кожна адреса | `localhost`, `2130706433`, DNS rebinding |
| перенаправлення вручну (`allow_redirects=False`), кожне — знову через `check_url` і resolver, максимум 3 | захист рядком обходили саме так |
| тайм-аут 10 с, до 2 000 000 байт (читаємо частинами по 64 КБ), тип `application/rss+xml`, `application/atom+xml`, `application/xml`, `text/xml` | повільний чи безкінечний сервер не тримає нас; відповідь — лише стрічка |
| `trust_env=False` | з `HTTP_PROXY` у середовищі з'єднання пішло б через проксі — повз наш resolver |

Розмір читається частинами, бо `Content-Length` може й не бути або бути неправдою:

```python title="news_hub/safe_fetch.py"
async def _read_limited(resp: aiohttp.ClientResponse, max_bytes: int) -> bytes:
    if resp.content_length is not None and resp.content_length > max_bytes:
        raise FetchError(f"відповідь {resp.content_length} байт — більше за {max_bytes}")
    body = bytearray()
    async for chunk in resp.content.iter_chunked(64 * 1024):        # Content-Length може й не бути
        body += chunk
        if len(body) > max_bytes:
            raise FetchError(f"відповідь більша за {max_bytes} байт")
    return bytes(body)
```

Покроково: `feed` — «зовнішній» сайт, `/to-metadata` відповідає `302` на адресу метаданих (тест `test_redirect_is_checked_again`):

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph H0 ["перенаправлення 0: http://feed/to-metadata"]
        direction LR
        h1{"check_url:<br>схема, порт"} -- "так" --> h2["PolicyResolver:<br>DNS → IP"] --> h3{"IP дозволена?"} -- "так" --> h4["GET → 302<br>Location: 169.254.169.254"]
    end
    subgraph H1 ["перенаправлення 1: http://169.254.169.254/latest/meta-data/"]
        direction LR
        k1{"check_url:<br>схема, порт"} -- "так" --> k2{"IP-літерал<br>публічна?"} -- "ні, link-local" --> k3["UnsafeURL →<br>400 заборонена адреса"]
    end
    subgraph R ["результат"]
        direction LR
        r1["внутрішній сервер:<br>0 запитів"] ~~~ r2["у базі:<br>нічого нового"]
    end
    H0 --> H1 --> R

    class h1,h3,k1,k2 decision
    class h2 step
    class h4 warning
    class k3 error
    class r1,r2 success
```

## Результат: перенаправлення на локальних серверах { #result-redirects }

Два aiohttp-сервери на `127.0.0.1`: `feed` з маршрутами-перенаправленнями і «внутрішній», що рахує, скільки запитів до нього дійшло. Політика — як у тестах: дозволено loopback, але **лише порт** `feed`:

```python
local = FetchPolicy(allow_ip=lambda ip: ip.is_loopback, allowed_ports=frozenset({feed.port}))
for path in ["/moved", "/to-internal", "/to-metadata", "/to-file", "/page", "/loop"]:
    await safe_fetch(str(feed.make_url(path)), local)
await safe_fetch("http://localhost/rss")            # політика за замовчуванням
```

```text
/moved        → OK redirects=1 chain=['/moved', '/rss'] bytes=2776
/to-internal  → UnsafeURL: порт 41337: дозволено [33587]
/to-metadata  → UnsafeURL: адреса 169.254.169.254 — link-local: сервер туди не звертається
/to-file      → UnsafeURL: схема file: дозволено лише http і https
/page         → FetchError: тип вмісту text/html: очікуємо RSS/XML
/loop         → FetchError: більше 3 перенаправлень
DEFAULT localhost → UnsafeURL: адреса 127.0.0.1 — loopback: сервер туди не звертається
запитів до внутрішнього сервера: 0
```

- **Звичайне перенаправлення** (`/moved → /rss`) працює: `redirects=1`, ланцюжок видно.
- **На внутрішній сервіс, метадані, `file://`** — відмова на **адресі з `Location`**, ще до з'єднання. Лічильник «внутрішнього» сервера — 0.
- **`UnsafeURL` проти `FetchError`.** Перше — «туди не можна» (`400`), друге — «можна, але не вийшло» (`502`).

## Ендпоінти джерел { #endpoints }

```python title="news_hub/api.py (фрагмент)"
def get_fetch_policy() -> FetchPolicy:
    """Що дозволено завантажувати. Тести підміняють: локальний сервер — лише там, де це явно потрібно."""
    return DEFAULT_POLICY


@app.post("/api/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED, tags=["admin"],
          summary="Додати RSS-джерело", dependencies=[AdminDep], ...)
async def create_source(body: SourceCreate, sources: SourcesDep, policy: FetchPolicyDep) -> SourceRow:
    """Перевірка без мережі (схема, порт, IP в адресі); DNS і з'єднання перевіряються при кожному збиранні."""
    try:
        url = str(check_url(body.url, policy))
    except UnsafeURL as error:
        raise unsafe(error) from error
    try:
        return await sources.create(url, body.name)
    except IntegrityError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"джерело {url} уже є") from error


@app.post("/api/sources/{source_id}/fetch", response_model=SourceFetchReport, tags=["admin"],
          summary="Зібрати новини з RSS-джерела", dependencies=[AdminDep], ...)
async def fetch_source(row: SourceDep, repo: RepoDep, policy: FetchPolicyDep) -> SourceFetchReport:
    """RSS → `parse_pravda_rss` (RSS 2.0) → `NewsItem` → база. Вміст відповіді назовні не віддаємо — лише підсумок."""
    try:
        result = await safe_fetch(row.url, policy)
    except UnsafeURL as error:
        raise unsafe(error) from error
    except FetchError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"джерело недоступне: {error}") from error
    ...
```

Ще два ендпоінти — `GET /api/sources` і `DELETE /api/sources/{source_id}`. Усі чотири — лише з `AdminDep`. Відповіді API (адмін з токеном):

```text
POST /api/sources http://169.254.169.254/latest/meta-data/ → 400 {'detail': 'заборонена адреса: адреса 169.254.169.254 — link-local: сервер туди не звертається'}
POST /api/sources http://localhost:6379/ → 400 {'detail': 'заборонена адреса: порт 6379: дозволено [80, 443]'}
POST /api/sources file:///etc/passwd → 400 {'detail': 'заборонена адреса: схема file: дозволено лише http і https'}
POST /api/sources http://[::ffff:127.0.0.1]/ → 400 {'detail': 'заборонена адреса: адреса 127.0.0.1 — loopback: сервер туди не звертається'}
POST /api/sources http://localhost/admin → 201 {'id': 1, 'url': 'http://localhost/admin'}
   POST /api/sources/1/fetch → 400 {'detail': 'заборонена адреса: адреса 127.0.0.1 — loopback: сервер туди не звертається'}
POST /api/sources http://2130706433/ → 201 {'id': 2, 'url': 'http://2130706433/'}
   POST /api/sources/2/fetch → 502 {'detail': 'джерело недоступне: InvalidUrlClientError: 2130706433 - is not a canonical IPv4 address'}
```

- **`http://localhost/admin` при додаванні проходить:** схема й порт у нормі, а ім'я без DNS не перевірити. Зупиняє resolver при завантаженні. Так і задумано: DNS міг змінитися між «додали» і «завантажили», тож перевірка — при **кожному** з'єднанні.
- **`http://2130706433/`** зупинила сама aiohttp (3.14): вона не приймає неканонічний запис IPv4 у URL. На версіях, які його приймають, адресу зупинить resolver — див. вивід вище. Захист не покладається на одну перевірку.
- **Відповідь — лише підсумок.** `SourceFetchReport` містить кількість знайдених, збережених і відхилених новин, а не тіло відповіді. Навіть якщо щось пройде, атакувальник не побачить, що там було. Такий SSRF називають «сліпим».

## Тести: «внутрішній» сервер, якого не можна торкатися { #tests }

У тестах обидва сервери на `127.0.0.1`. Політика розширюється **явно**, параметром через `dependency_overrides`, а не змінною середовища: змінну можна забути на сервері, а параметр видно в коді тесту.

```python title="tests/integration/test_sources_ssrf.py (фрагмент)"
@pytest.fixture
def local_policy(feed: TestServer) -> FetchPolicy:
    policy = FetchPolicy(allow_ip=lambda ip: ip.is_loopback, allowed_ports=frozenset({feed.port}),
                         max_bytes=1_000_000)
    app.dependency_overrides[get_fetch_policy] = lambda: policy
    return policy
```

«Внутрішній» недосяжний, бо дозволено лише порт `feed` — як у справжній мережі, де до внутрішнього сервісу немає маршруту. Маршрут `/to-metadata` перенаправляє на `169.254.169.254` **з тим самим портом**, що й `feed`, щоб спрацювала перевірка IP, а не порту. Повний перелік тестів — у [Тестах безпеки](security_tests.md#files).

## Межі { #limits }

- **Allowlist доменів новин** (`NewsItem.only_allowed`: `rbc.ua`, `pravda.com.ua`, `epravda.com.ua`) — правило **вмісту**: чиї новини ми зберігаємо. `safe_fetch` — правило **мережі**: куди сервер з'єднується. Одне не замінює іншого.
- **`scraper.py`** (крок 2) ходить лише на сторінки rbc.ua (`is_rbc_host`), але через звичайний `aiohttp.ClientSession()`: перенаправлення за ним aiohttp виконує сам, без перевірки IP. Це завдання [«Спробуй самостійно»](checkpoint.md#try-yourself).
- **`is_global` не знає всього.** Для `64:ff9b::a9fe:a9fe` (NAT64-запис `169.254.169.254`) і `::127.0.0.1` (застарілий IPv4-сумісний запис) `is_public_ip` повертає `True` (Python 3.12):

    ```text
    64:ff9b::a9fe:a9fe        public=True
    ::127.0.0.1               public=True
    ```

    У мережі з NAT64 перша адреса справді веде до метаданих. Якщо сервер працює в такій мережі, `allow_ip` варто звузити: власна функція в `FetchPolicy`.

Як обрати захист, коли сервер завантажує URL:

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    Q1{"URL задає людина<br>чи інша система?"} -- "ні, лише код" --> A1["константа в коді<br>PAGES у scraper.py"]
    Q1 -- "так" --> Q2{"набір сайтів<br>відомий наперед?"}
    Q2 -- "так" --> A2["allowlist хостів<br>+ перевірка перенаправлень"]
    Q2 -- "ні" --> A3["safe_fetch: IP після DNS,<br>порти, розмір, тип"]
    A2 --> W["у будь-якому разі:<br>відповідь не віддавати як є"]
    A3 --> W

    class Q1,Q2 decision
    class A1,A2,A3 success
    class W warning
```

Поглиблено: [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html); Python — [`ipaddress`](https://docs.python.org/3/library/ipaddress.html); aiohttp — [Resolvers](https://docs.aiohttp.org/en/stable/client_reference.html#resolvers).

## Правило { #rule }

!!! tip "Правило"
    Перевіряй не рядок URL, а **IP, до якого з'єднується сервер**: у resolver з'єднання, для кожної адреси з DNS і для кожного перенаправлення. Схема, порт, логін в URL — до мережі; тайм-аут, розмір і тип — під час читання. Назовні віддавай підсумок, а не відповідь чужого сервера. Політику розширюй лише явно, параметром.

**Далі:** [Підписані webhook](webhooks.md).
