#!/usr/bin/env bash
# Бекап бази news_hub з контейнера PostgreSQL. Урок 49.
#   ./scripts/backup.sh [папка]          → backups/news_hub-20260928-101500.sql.gz
# На сервері — щоночі з cron:  15 3 * * *  cd /srv/news_hub && ./scripts/backup.sh >> backups/backup.log 2>&1
set -euo pipefail        # pipefail: без нього впалий pg_dump дав би «успішний» порожній архів (бонус-урок Linux)

cd "$(dirname "$0")/.."
dir="${1:-backups}"
mkdir -p "$dir"
file="$dir/news_hub-$(date +%Y%m%d-%H%M%S).sql.gz"
trap 'rm -f "$file.tmp"' EXIT                   # впало посередині — недописаного файлу не лишаємо

# --clean --if-exists: у дампі є DROP перед CREATE — відновлення працює і поверх наявної бази
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
    | gzip > "$file.tmp"
mv "$file.tmp" "$file"
echo "бекап: $file ($(du -h "$file" | cut -f1))"
