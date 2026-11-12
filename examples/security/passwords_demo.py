"""Хешування паролів: чому не sha256, сіль, вартість, bcrypt і Argon2, порівняння за сталий час.

python passwords_demo.py

Паролі тут вигадані, «злита база» — словник у пам'яті. Час залежить від машини.
"""
import hashlib
import hmac
import secrets
import time
import timeit

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


def title(text: str) -> None:
    print(f"--- {text}")


def seconds(fn, number: int = 1) -> float:
    start = time.perf_counter()
    for _ in range(number):
        fn()
    return (time.perf_counter() - start) / number


# ---------------------------------------------------------------------------
title("1. sha256 без солі: «злита база» і словник")
users = {"olena": "qwerty123", "taras": "qwerty123", "ivan": "Kyiv2024!", "maria": "x7#Lp9!vQ2@zR4"}
leaked = {name: hashlib.sha256(pw.encode()).hexdigest() for name, pw in users.items()}
for name, digest in leaked.items():
    print(f"   {name:6} {digest[:16]}…")
print("   однакові паролі видно без злому:", leaked["olena"] == leaked["taras"])

wordlist = ["123456", "password", "qwerty123", "Kyiv2024!", "iloveyou", "admin"] + [f"pass{n}" for n in range(100_000)]
start = time.perf_counter()
table = {hashlib.sha256(word.encode()).hexdigest(): word for word in wordlist}       # порахували ОДИН раз
cracked = {name: table[d] for name, d in leaked.items() if d in table}
print(f"   словник {len(wordlist)} слів → зламано {sorted(cracked)} за {time.perf_counter() - start:.2f} с")

# ---------------------------------------------------------------------------
title("2. швидкість одного хешу: sha256, bcrypt, Argon2id")
sha = seconds(lambda: hashlib.sha256(b"qwerty123").digest(), 100_000)
bc12 = seconds(lambda: bcrypt.hashpw(b"qwerty123", bcrypt.gensalt(12)), 3)
ph = PasswordHasher()                                                    # параметри бібліотеки за замовчуванням
a2 = seconds(lambda: ph.hash("qwerty123"), 3)
for name, t in (("sha256", sha), ("bcrypt rounds=12", bc12), ("argon2id (за замовчуванням)", a2)):
    print(f"   {name:28} {t * 1000:10.4f} мс   ≈ {1 / t:>12,.0f} спроб/с на ядро")
print(f"   bcrypt повільніший за sha256 у ~{bc12 / sha:,.0f} разів")

# ---------------------------------------------------------------------------
title("3. сіль: той самий пароль — різні хеші")
h1, h2 = bcrypt.hashpw(b"qwerty123", bcrypt.gensalt(4)), bcrypt.hashpw(b"qwerty123", bcrypt.gensalt(4))
print("   bcrypt :", h1.decode())
print("   bcrypt :", h2.decode())
print("   різні:", h1 != h2, "| обидва перевіряються:", bcrypt.checkpw(b"qwerty123", h1), bcrypt.checkpw(b"qwerty123", h2))
s = h1.decode()
print(f"   будова : алгоритм {s[1:3]!r}, вартість {s[4:6]!r}, сіль {s[7:29]!r} (22), хеш {s[29:]!r} (31)")
a = ph.hash("qwerty123")
print("   argon2 :", a)
print("   параметри в рядку:", a.split("$")[3])

# ---------------------------------------------------------------------------
title("4. вартість bcrypt: +1 раунд — удвічі довше")
for rounds in (10, 11, 12, 13):
    salt = bcrypt.gensalt(rounds)
    print(f"   rounds={rounds}: {seconds(lambda: bcrypt.hashpw(b'qwerty123', salt), 2):.3f} с")

# ---------------------------------------------------------------------------
title("5. межа bcrypt — 72 байти; Argon2 її не має")
long_pw = "я" * 37                                                        # 74 байти UTF-8
print("   len(str) =", len(long_pw), "| len(bytes) =", len(long_pw.encode()))
try:
    bcrypt.hashpw(long_pw.encode(), bcrypt.gensalt(4))
except ValueError as error:
    print("   bcrypt.hashpw:", type(error).__name__, "—", error)
print("   argon2:", ph.verify(ph.hash(long_pw), long_pw))

# ---------------------------------------------------------------------------
title("6. перевірка і «перехешування» при вході")
old = PasswordHasher(time_cost=1, memory_cost=8 * 1024)                    # «старі» параметри
stored = old.hash("Kyiv2024!")
try:
    ph.verify(stored, "kyiv2024!")
except VerifyMismatchError as error:
    print("   неправильний пароль:", type(error).__name__)
print("   правильний:", ph.verify(stored, "Kyiv2024!"), "| check_needs_rehash:", ph.check_needs_rehash(stored))
stored = ph.hash("Kyiv2024!")                                              # після вдалого входу — новий хеш
print("   після перехешування:", stored.split("$")[3], "| needs_rehash:", ph.check_needs_rehash(stored))
bc_old = bcrypt.hashpw(b"Kyiv2024!", bcrypt.gensalt(10)).decode()
print("   bcrypt: вартість у хеші", int(bc_old.split("$")[2]), "< 12 → перехешувати:", int(bc_old.split("$")[2]) < 12)

# ---------------------------------------------------------------------------
title("7. == проти hmac.compare_digest: час залежить від першої розбіжності")
secret = secrets.token_bytes(1_000_000)                                     # великий рядок — щоб різницю було видно
early = b"X" + secret[1:]                                                  # відрізняється в першому байті
late = secret[:-1] + b"X"                                                  # відрізняється в останньому
for name, fn in (("==", lambda x: secret == x), ("compare_digest", lambda x: hmac.compare_digest(secret, x))):
    t_early = min(timeit.repeat(lambda: fn(early), number=200, repeat=5)) / 200
    t_late = min(timeit.repeat(lambda: fn(late), number=200, repeat=5)) / 200
    print(f"   {name:15} перший байт: {t_early * 1e6:8.2f} мкс | останній: {t_late * 1e6:8.2f} мкс")

# ---------------------------------------------------------------------------
title("8. вхід: «немає такого користувача» за часом")
db = {"olena": bcrypt.hashpw(b"Kyiv2024!", bcrypt.gensalt(12))}
DUMMY_HASH = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt(12))    # хеш, якого ніхто не знає


def login_leaky(username: str, password: str) -> bool:
    stored = db.get(username)
    if stored is None:
        return False                                                       # миттєво — і цим видає, що імені немає
    return bcrypt.checkpw(password.encode(), stored)


def login_even(username: str, password: str) -> bool:
    stored = db.get(username)
    ok = bcrypt.checkpw(password.encode(), stored or DUMMY_HASH)          # bcrypt завжди
    return ok and stored is not None


for fn in (login_leaky, login_even):
    known = seconds(lambda: fn("olena", "guess"), 2)
    unknown = seconds(lambda: fn("nobody", "guess"), 2)
    print(f"   {fn.__name__:12} відоме ім'я: {known:.3f} с | невідоме: {unknown:.3f} с")
