# Частина X. Docker, Compose і CI/CD

Образ застосунку, система з кількох контейнерів, деплой на сервер і автоматична перевірка кожної зміни.

## Розділи

| Розділ | Код | Стан |
|---|---|---|
| [Docker-образ](docker_image.md) | `steps/10/Dockerfile`, `.dockerignore` | готово |
| [Docker Compose](compose.md) | `steps/11/docker-compose.yml`, `nginx/` | готово |
| [Сервер у production](production_server.md) | — | готово |
| [CI/CD на GitHub Actions](ci_cd.md) | `.github/workflows/news_hub.yml` | готово |
| [Мікросервіси: коли варто](microservices.md) | — | готово |

## На практиці — Zero to Hero

- [Крок 10. Docker-образ](../tutorials/10_docker/index.md) — `steps/10_docker`
- [Крок 11. Docker Compose і деплой](../tutorials/11_compose_deploy/index.md) — `steps/11_compose_deploy`
- [Крок 12. CI/CD на GitHub Actions](../tutorials/12_ci_cd/index.md) — `steps/12_ci_cd`
