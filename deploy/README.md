# Deploy (test site, "bench")

The whole system on one Linux server with Docker Compose ([compose.yaml](compose.yaml)):

| Service | What it does |
|---|---|
| `web` | Caddy: HTTPS (Let's Encrypt, automatic), `/pt-PT/` and `/en/`, `/v1` to the API, `noindex`, and the test site's password on `/mail` ([Caddyfile](Caddyfile)) |
| `api` | FastAPI; runs the migrations on start |
| `db` | MySQL 8.0 (data in the `mysql_data` volume) |
| `scheduler` | reminders and automatic cancellations at every :00 and :30 |
| `backup` | a copy of the database every day in `backups/`, the last 14 kept |
| `mailpit` | catches every email: nothing reaches real clients from the test site (see `/mail`) |

Images are built on the server from the two repositories, side by side:

```
~/nailsbyscooby/
├── bx-sch-4-nbs/        (this one: API + deploy/)
└── bx-sch-4-nbs-front/  (the site)
```

## First install (Ubuntu 24.04, e.g. Oracle Cloud Always Free)

```bash
# 1. Log in (from the computer that has the key)
ssh -i ~/.ssh/nailsbyscooby_oracle ubuntu@<server IP>

# 2. Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit        # log in again for the group to apply

# 3. Oracle's Ubuntu images block everything but SSH in their own firewall: open 80 and 443
sudo iptables -I INPUT 6 -p tcp -m state --state NEW --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -p tcp -m state --state NEW --dport 443 -j ACCEPT
sudo netfilter-persistent save

# 4. The code (the test site follows the release branches)
mkdir -p ~/nailsbyscooby && cd ~/nailsbyscooby
git clone -b uat https://github.com/beatriz-oz/bx-sch-4-nbs.git
git clone -b main https://github.com/beatriz-oz/bx-sch-4-nbs-front.git

# 5. Secrets: creates .env (random keys) and the password of /mail (the caught emails)
cd bx-sch-4-nbs/deploy
sh new-secrets.sh <login name>
nano .env        # check SITE_ADDRESS and PUBLIC_URL (the DuckDNS / own domain)

# 6. Start everything (the first build takes a few minutes)
docker compose up -d --build

# 7. The studio's admin account, then publish the policies in the admin
docker compose exec api python -m bx_sch_4_nbs.scripts.create_admin
```

The domain must point to the server **before** step 6 (DuckDNS: "current ip"), or Caddy cannot get the certificate.
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

**Real emails (Brevo):** fill the `SMTP_*` and `EMAIL_FROM` lines in `.env`, then `docker compose up -d`.

## Try it on a computer

In `.env`: `SITE_ADDRESS=:80`, `HTTP_PORT=8088`, `PUBLIC_URL=http://localhost:8088`, then `docker compose up -d --build` and open <http://localhost:8088> (no HTTPS locally).
