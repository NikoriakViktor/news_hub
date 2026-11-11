#!/usr/bin/env bash
# Smoke-тест усього стеку в Compose: так його запускає CI (урок 50), так само можна локально.
#   ADMIN_PASSWORD=… ./scripts/smoke.sh        (потрібен .env: python scripts/make_env.py)
# Піднімає стек, проходить шлях користувача через nginx і завжди прибирає за собою (docker compose down -v).
set -euo pipefail

cd "$(dirname "$0")/.."
: "${ADMIN_PASSWORD:?задай ADMIN_PASSWORD — той самий, з яким створено .env}"
port="$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 | tr -d "'")"
base="http://localhost:${port:-80}"

cleanup() {
    status=$?
    if [[ $status -ne 0 ]]; then
        echo "--- smoke впав (код $status): стан і журнали ---" >&2
        docker compose ps -a >&2 || true
        docker compose logs --tail 60 >&2 || true
    fi
    docker compose down -v --remove-orphans > /dev/null 2>&1 || true
}
trap cleanup EXIT

check() {                          # check "назва" очікуване фактичне
    if [[ "$2" != "$3" ]]; then
        echo "✗ $1: очікували $2, отримали $3" >&2
        exit 1
    fi
    echo "✓ $1"
}

docker compose up -d --build --wait --wait-timeout 180

check "готовність через nginx" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$base/health/ready")"
check "nginx відповідає" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$base/nginx-health")"

token="$(curl -sf -X POST "$base/api/admin/token" -H 'content-type: application/json' \
    -d "{\"username\": \"admin\", \"password\": \"$ADMIN_PASSWORD\"}" | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')"
check "вхід адміна" true "$([[ -n "$token" ]] && echo true || echo false)"

check "запис без токена" 401 "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$base/api/scrape" \
    -H 'content-type: application/json' -d '{"source": "snapshot"}')"
saved="$(curl -sf -X POST "$base/api/scrape" -H "Authorization: Bearer $token" -H 'content-type: application/json' \
    -d '{"source": "snapshot"}' | python3 -c 'import sys, json; print(json.load(sys.stdin)["news_saved"])')"
check "збір зі знімка" 168 "$saved"
check "новини в PostgreSQL" '{"count":168}' "$(curl -sf "$base/api/news/count")"

check "база й Redis без портів назовні" "" "$(docker compose ps postgres redis --format '{{.Ports}}' | grep -- '->' || true)"
echo "smoke: усе гаразд"
