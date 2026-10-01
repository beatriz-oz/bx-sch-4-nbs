import logging
from datetime import datetime, timedelta

from sqlmodel import Session

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.queries.schedule import (
    appointments_needing_reminder,
    appointments_to_auto_cancel,
    auto_cancel_appointment,
    mark_reminder_sent,
)
from bx_sch_4_nbs.helpers.authentication import create_attendance_token
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.helpers.email import (
    send_attendance_reminder,
    send_auto_cancelled_notification_client,
    send_auto_cancelled_notification_studio,
)
from bx_sch_4_nbs.helpers.security import decrypt_email

logger = logging.getLogger(__name__)


def process_reminders(session: Session, now: datetime) -> int:
    count = 0

    for appointment in appointments_needing_reminder(session, now):
        client = session.get(User, appointment.user_id)
        if client is None or appointment.id is None:
            continue

        deadline = appointment.scheduled_at - timedelta(hours=settings.confirmation_deadline_hours_before)

        appointment_date = to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M")
        token = create_attendance_token(appointment.id, deadline)
        email_client = decrypt_email(client.email_encrypted)

        email_sent = send_attendance_reminder(
            email_client,
            appointment_date,
            to_studio_time(deadline).strftime("%d/%m/%Y %H:%M"),
            token,
        )

        if email_sent:
            mark_reminder_sent(session, appointment, now)
            session.commit()
            count += 1

    return count


def process_auto_cancellations(session: Session, now: datetime) -> int:
    count = 0

    for appointment in appointments_to_auto_cancel(session, now):
        client = session.get(User, appointment.user_id)
        if client is None or appointment.id is None:
            continue

        appointment_date = to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M")
        email_client = decrypt_email(client.email_encrypted)
        is_deposit_paid = appointment.deposit_paid_at is not None

        auto_cancel_appointment(session, appointment, now)
        session.commit()

        email_sent = send_auto_cancelled_notification_client(
            email_client,
            appointment_date,
        )

        send_auto_cancelled_notification_studio(
            settings.studio_notification_email,
            client.instagram,
            f"{client.name} {client.last_name}",
            appointment_date,
            is_deposit_paid,
            email_sent,
        )

        count += 1

    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = utc_now()
    logger.info("Processing appointments at %s (UTC)", now)

    with engine.connect() as connection:
        session = Session(bind=connection)
        reminders = process_reminders(session, now)
        cancellations = process_auto_cancellations(session, now)

    logger.info("Done. Reminders sent: %d, auto-cancelled: %d", reminders, cancellations)


if __name__ == "__main__":
    main()
