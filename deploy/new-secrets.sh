#!/bin/sh
# Creates deploy/.env (with new random secrets) and deploy/bench-auth.caddy (the test site's login).
# Run it once on the server, from the deploy folder:   sh new-secrets.sh <login name>
# It never overwrites: delete a file first to create it again (a new ENCRYPTION_KEY or HASH_PEPPER
# makes the data already stored unreadable, so keep a copy of .env somewhere safe).
set -eu
cd "$(dirname "$0")"

user="${1:-}"
if [ -z "$user" ]; then
    echo "Usage: sh new-secrets.sh <login name for the test site>" >&2
    exit 1
fi

hex() { openssl rand -hex "$1"; }

if [ -e .env ]; then
    echo ".env already exists: kept as it is."
else
    # Fernet needs 32 random bytes in URL-safe base64.
    fernet=$(openssl rand -base64 32 | tr '+/' '-_')
    sed -e "s|^MYSQL_PASSWORD=.*|MYSQL_PASSWORD=$(hex 24)|" \
        -e "s|^MYSQL_ROOT_PASSWORD=.*|MYSQL_ROOT_PASSWORD=$(hex 24)|" \
        -e "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$fernet|" \
        -e "s|^HASH_PEPPER=.*|HASH_PEPPER=$(hex 32)|" \
        -e "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$(hex 32)|" \
        .env.example > .env
    chmod 600 .env
    echo "Created .env with new secrets. Check SITE_ADDRESS and PUBLIC_URL in it."
fi

if [ -e bench-auth.caddy ]; then
    echo "bench-auth.caddy already exists: kept as it is."
else
    printf "Password for the test site (login: %s): " "$user"
    stty -echo 2>/dev/null || true
    read -r password
    stty echo 2>/dev/null || true
    echo
    # A password pasted on Windows may end in an invisible carriage return: drop it.
    password=$(printf '%s' "$password" | tr -d '\r')
    # Caddy stores only a bcrypt hash of it, never the password itself.
    hash=$(docker run --rm caddy:2-alpine caddy hash-password --plaintext "$password")
    printf 'basic_auth {\n\t%s %s\n}\n' "$user" "$hash" > bench-auth.caddy
    chmod 600 bench-auth.caddy
    echo "Created bench-auth.caddy."
fi
