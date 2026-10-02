from datetime import datetime

from sqlmodel import Session

from bx_sch_4_nbs.database.exceptions import (
    AppointmentNotActiveError,
    ResourceDoesNotExistError,
)
from bx_sch_4_nbs.database.models import Appointment, User
from bx_sch_4_nbs.database.queries import schedule
from bx_sch_4_nbs.database.types import AppointmentStatus


def confirm_deposit(session: Session, appointment_id: int, now: datetime) -> tuple[Appointment, User, bool]:
    appointment = session.get(Appointment, appointment_id)

    if not appointment:
        raise ResourceDoesNotExistError("The appointment does not exist")

    user = session.get(User, appointment.user_id)
    if not user:
        raise ResourceDoesNotExistError("The user does not exist")

    if appointment.status not in schedule.ACTIVE_STATUSES:
        raise AppointmentNotActiveError(
            f"Appointment cannot be confirmed, the current status is: {appointment.status.value}"
        )

    if appointment.deposit_paid_at is not None:
        return appointment, user, False

    appointment.status = AppointmentStatus.CONFIRMED
    appointment.deposit_paid_at = now
    session.add(appointment)
    session.flush()

    return appointment, user, True
