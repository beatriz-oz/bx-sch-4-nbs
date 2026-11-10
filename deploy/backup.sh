#!/bin/sh
# Runs in the "backup" container: a compressed copy of the database at start, then every 24 hours.
# Copies older than KEEP_DAYS are deleted. Restore one with:
#   gunzip -c backups/<file>.sql.gz | docker compose exec -T db mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"
set -u

while true; do
    file="/backups/${MYSQL_DATABASE}-$(date -u +%Y-%m-%d_%H%M).sql.gz"
    # --single-transaction: a consistent copy without locking the tables while the site is in use.
    if mysqldump -h db -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --no-tablespaces "$MYSQL_DATABASE" | gzip > "$file.tmp"; then
        mv "$file.tmp" "$file"
        echo "backup: $file"
    else
        rm -f "$file.tmp"
        echo "backup FAILED" >&2
    fi
    find /backups -name '*.sql.gz' -mtime "+${KEEP_DAYS}" -delete
    sleep 86400
done
