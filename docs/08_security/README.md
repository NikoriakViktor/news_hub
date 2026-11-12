# Частина VIII. Безпека API

Хеш пароля (bcrypt), JWT і ролі, SSRF при завантаженні чужих URL, підписані webhook з HMAC і захистом від повтору.

## Розділи

| Розділ | Код | Стан |
|---|---|---|
| [Паролі: хеш, сіль, вартість](passwords.md) | `steps/08/news_hub/security.py` | готово |
| [Автентифікація: сесії і JWT](authentication.md) | — | готово |
| [Авторизація: ролі, scopes, об'єкти](authorization.md) | — | готово |
| [SSRF і вихідні запити](ssrf_and_outbound.md) | `steps/08/news_hub/safe_fetch.py` | готово |
| [Webhook і підписи](webhooks_and_signatures.md) | `steps/08/news_hub/webhooks.py` | готово |
| [Секрети, заголовки, проксі](secrets_and_headers.md) | `SECRET_KEY`, `check --deploy` | готово |
| [OWASP API Top 10](owasp_api_top10.md) | — | готово |

## На практиці — Zero to Hero

- [Крок 8. Безпека: JWT, SSRF, webhook](../tutorials/08_security/index.md) — `steps/08_security`
