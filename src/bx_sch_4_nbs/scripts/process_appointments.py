import logging
from datetime import datetime

from sqlmodel import Session

from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.queries.schedule import (
    appointments_needing_reminder,
    mark_reminder_sent,
)
from bx_sch_4_nbs.helpers.authentication import create_attendance_token
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.helpers.email import send_attendance_reminder
from bx_sch_4_nbs.helpers.security import email_or_none

logger = logging.getLogger(__name__)


def process_reminders(session: Session, now: datetime) -> int:
    count = 0

    for appointment in appointments_needing_reminder(session, now):
        client = session.get(User, appointment.user_id)
        if client is None or appointment.id is None:
            continue

        appointment_date = to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M")
        # Confirming is optional: the link works until the appointment starts.
        token = create_attendance_token(appointment.id, appointment.scheduled_at)
        email_client = email_or_none(client.email_encrypted)
        if email_client is None:
            # A regular client without an email yet: not marked as sent, so it still goes out
            # if she checks in before the appointment.
            continue

        email_sent = send_attendance_reminder(email_client, appointment_date, token)

        if email_sent:
            mark_reminder_sent(session, appointment, now)
            session.commit()
            count += 1

    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = utc_now()
    logger.info("Processing appointments at %s (UTC)", now)

    with engine.connect() as connection:
        session = Session(bind=connection)
        reminders = process_reminders(session, now)

    logger.info("Done. Reminders sent: %d", reminders)


if __name__ == "__main__":
    main()
