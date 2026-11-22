# Deploy

The whole system on one Linux server with Docker Compose ([compose.yaml](compose.yaml)), in one of two modes
(`DEPLOY_MODE` in `.env`):

| Mode | Emails | Search engines | Extra rules |
|---|---|---|---|
| `production` | sent for real (Brevo SMTP) | allowed | none ([caddy/production.caddy](caddy/production.caddy)) |
| `bench` (test site) | caught by Mailpit at `/mail`, behind a password | `noindex` | [caddy/bench.caddy](caddy/bench.caddy); also `COMPOSE_PROFILES=bench` |

| Service | What it does |
|---|---|
| `web` | Caddy: HTTPS (Let's Encrypt, automatic), `/pt-PT/` and `/en/`, `/v1` to the API, plus the mode's rules ([Caddyfile](Caddyfile)) |
| `api` | FastAPI; runs the migrations on start |
| `db` | MySQL 8.0 (data in the `mysql_data` volume) |
| `scheduler` | reminder emails at every :00 and :30 |
| `backup` | a copy of the database every day in `backups/`, the last 14 kept |
| `mailpit` | bench only: catches every email, nothing reaches real clients (see `/mail`) |

Images are built on the server from the two repositories, side by side:

```
~/nailsbyscooby/
├── bx-sch-4-nbs/        (this one: API + deploy/)
└── bx-sch-4-nbs-front/  (the site)
```

## First install (Ubuntu 24.04, e.g. OVHcloud VPS)

```bash
# 1. Log in (from the computer that has the key)
ssh -i ~/.ssh/nailsbyscooby_prod ubuntu@<server IP>

# 2. Docker, and a firewall that only lets in SSH, HTTP and HTTPS
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw --force enable
exit        # log in again for the docker group to apply

# 3. The code. Production follows main in both repositories; a test site would follow uat (back end).
mkdir -p ~/nailsbyscooby && cd ~/nailsbyscooby
git clone -b main https://github.com/beatriz-oz/bx-sch-4-nbs.git
git clone -b main https://github.com/beatriz-oz/bx-sch-4-nbs-front.git

# 4. Secrets: creates .env with random keys
cd bx-sch-4-nbs/deploy
sh new-secrets.sh production          # a test site: sh new-secrets.sh bench <login name for /mail>
nano .env        # SITE_ADDRESS and PUBLIC_URL (the domain), then the SMTP_* lines and EMAIL_FROM

# 5. Start everything (the first build takes a few minutes)
docker compose up -d --build

# 6. The studio's admin account, then publish the policies in the admin
docker compose exec api python -m bx_sch_4_nbs.scripts.create_admin
```

The domain must point to the server **before** step 5 (an `A` record to the server's IP), or Caddy cannot get the certificate.
Keep a copy of `.env` somewhere safe: without `ENCRYPTION_KEY` and `HASH_PEPPER` the stored data cannot be read.

## Update to the latest version

```bash
cd ~/nailsbyscooby/bx-sch-4-nbs && git pull
cd ../bx-sch-4-nbs-front && git pull
cd ../bx-sch-4-nbs/deploy && docker compose up -d --build
```

## Day to day

```bash
docker compose ps                    # what is running
docker compose logs -f api           # logs of one service (api, web, scheduler, backup…)
docker compose exec api python -m bx_sch_4_nbs.scripts.seed_demo    # demo data (after the policies)
```

**Restore a backup:**

```bash
gunzip -c backups/<file>.sql.gz | docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
```

**Emails (Brevo):** the `SMTP_*` and `EMAIL_FROM` lines in `.env`, then `docker compose up -d`. Brevo must allow the server's IP.

## Try it on a computer

In `.env`: `SITE_ADDRESS=:80`, `HTTP_PORT=8088`, `PUBLIC_URL=http://localhost:8088`, then `docker compose up -d --build` and open <http://localhost:8088> (no HTTPS locally).
