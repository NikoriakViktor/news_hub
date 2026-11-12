#!/usr/bin/env sh
# Самопідписаний сертифікат для localhost на 1 день — лише для прикладу. На сервері — Let's Encrypt.
set -eu
cd "$(dirname "$0")"
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=localhost" \
    -keyout certs/key.pem -out certs/cert.pem 2>/dev/null
chmod 644 certs/key.pem          # nginx читає ключ від свого користувача; у справжньому стеку — 600 і власник
echo "certs/cert.pem, certs/key.pem"
