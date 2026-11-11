#!/usr/bin/env bash
# Відновити базу news_hub з бекапу. Урок 49.   ./scripts/restore.sh backups/news_hub-….sql.gz
# Поточні дані в базі буде ЗАМІНЕНО даними з бекапу.
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ $# -ne 1 || ! -f "$1" ]]; then
    echo "usage: scripts/restore.sh BACKUP.sql.gz" >&2
    exit 2
fi

gunzip -c "$1" | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q -o /dev/null'
docker compose exec -T redis redis-cli FLUSHDB > /dev/null     # кеш стрічки й статистики — від старих даних
echo "відновлено з $1"
