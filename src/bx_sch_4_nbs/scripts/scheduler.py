"""
Runs process_appointments at every :00 and :30, for ever: the "cron" of the Docker deploy.

    uv run python -m bx_sch_4_nbs.scripts.scheduler

A tiny loop instead of a cron daemon inside the container: nothing else to install, and the
logs go straight to `docker compose logs scheduler`. Aligned to :00 and :30 because the slots
start on the hour, so a reminder or an automatic cancellation is never more than 30 minutes late.
One failed run is logged and the next one still happens.
"""

import logging
import time
from datetime import UTC, datetime, timedelta

from bx_sch_4_nbs.scripts import process_appointments

logger = logging.getLogger(__name__)


def seconds_until_next_half_hour(now: datetime) -> float:
    """From 10:07:30 to 10:30:00 -> 1350 seconds. Exactly on :00 or :30 waits a full half hour."""
    next_run = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0) + timedelta(minutes=30)
    return (next_run - now).total_seconds()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Scheduler started: process_appointments at every :00 and :30 (UTC).")
    while True:
        time.sleep(seconds_until_next_half_hour(datetime.now(UTC)))
        try:
            process_appointments.main()
        except Exception:
            logger.exception("process_appointments failed; trying again at the next half hour.")


if __name__ == "__main__":
    main()
