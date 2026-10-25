"""
Changing an appointment that is still active: the studio can change anything at any time,
the client only her own, and only more than free_cancellation_hours before.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.exceptions import (
    AppointmentChangeNotAllowedError,
    AppointmentNotActiveError,
    DuplicateResourceError,
    ResourceDoesNotExistError,
)
from bx_sch_4_nbs.database.models import Appointment, BookedSlot
from bx_sch_4_nbs.database.queries import availability, day_slots, prices
from bx_sch_4_nbs.database.queries.schedule import ACTIVE_STATUSES, is_change_window_open
from bx_sch_4_nbs.database.types import NailArtLevel, NailSize, Service
from bx_sch_4_nbs.helpers.common import to_studio_time


@dataclass
class ChangedAppointment:
    appointment: Appointment
    previous_scheduled_at: datetime

    @property
    def time_changed(self) -> bool:
        return self.appointment.scheduled_at != self.previous_scheduled_at


def get_active_appointment(session: Session, appointment_id: int) -> Appointment:
    appointment = session.get(Appointment, appointment_id)
    if appointment is None:
        raise ResourceDoesNotExistError(f"Appointment {appointment_id} does not exist.")
    if appointment.status not in ACTIVE_STATUSES:
        raise AppointmentNotActiveError("Only scheduled or confirmed appointments can be changed.")
    return appointment


def move_appointment(
    session: Session, appointment: Appointment, scheduled_at: datetime, attendance_confirmed_at: datetime | None
) -> None:
    """
    Moves the appointment and its booked slot. The reminder and the attendance confirmation
    were about the old time, so they start again.
    """
    if scheduled_at == appointment.scheduled_at:
        return
    if appointment.id is None:
        raise RuntimeError("Appointment without id.")

    old_slot = session.get(BookedSlot, appointment.scheduled_at)
    if old_slot is not None:
        session.delete(old_slot)
        session.flush()

    appointment.scheduled_at = scheduled_at
    appointment.reminder_sent_at = None
    appointment.attendance_confirmed_at = attendance_confirmed_at
    session.add(appointment)
    session.add(BookedSlot(slot_at=scheduled_at, appointment_id=appointment.id))
    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateResourceError("This time is already booked. Please choose another one.") from error


def change_appointment_by_client(
    session: Session,
    appointment_id: int,
    user_id: int,
    *,
    scheduled_at: datetime,
    service: Service,
    nail_size: NailSize | None,
    nail_art_level: NailArtLevel | None,
    broken_nails: int,
    has_other_professional_nails: bool,
    now: datetime,
) -> tuple[ChangedAppointment, prices.Estimate]:
    appointment = session.get(Appointment, appointment_id)
    # Someone else's appointment answers as if it did not exist (no hint that the id is used).
    if appointment is None or appointment.user_id != user_id:
        raise ResourceDoesNotExistError(f"Appointment {appointment_id} does not exist.")
    if appointment.status not in ACTIVE_STATUSES:
        raise AppointmentNotActiveError("Only scheduled or confirmed appointments can be changed.")
    if appointment.service == Service.OTHER:
        raise AppointmentChangeNotAllowedError(
            "This appointment was arranged directly with the studio. To change it, contact @nailsbyscooby on Instagram."
        )
    if not is_change_window_open(appointment.scheduled_at, now):
        raise AppointmentChangeNotAllowedError(
            f"Appointments can only be changed more than {settings.free_cancellation_hours} hours before. "
            "Contact @nailsbyscooby on Instagram."
        )

    if scheduled_at == appointment.scheduled_at:
        # Same time: her own booking keeps it, only the nail size could rule it out (XL/XXL).
        local = to_studio_time(scheduled_at)
        if not availability.is_slot_allowed_for_size(
            local.time(), nail_size, day_slots.slots_for_day(session, local.date())
        ):
            raise AppointmentChangeNotAllowedError(
                "XL and XXL nails only go in the first or the last time of the day. Please choose another time."
            )
    elif not availability.is_slot_available(session, scheduled_at, nail_size):
        raise DuplicateResourceError("This time is not available. Please choose another one.")

    estimate = prices.estimate_price(
        session,
        user_id=user_id,
        scheduled_at=scheduled_at,
        service=service,
        nail_size=nail_size,
        nail_art_level=nail_art_level,
        broken_nails=broken_nails,
        has_other_professional_nails=has_other_professional_nails,
    )

    previous = appointment.scheduled_at
    move_appointment(session, appointment, scheduled_at, attendance_confirmed_at=None)
    appointment.service = estimate.service
    appointment.nail_size = nail_size
    appointment.nail_art_level = nail_art_level
    appointment.broken_nails = broken_nails
    appointment.has_other_professional_nails = has_other_professional_nails
    appointment.estimated_price = estimate.estimated_price
    session.add(appointment)
    session.flush()
    return ChangedAppointment(appointment, previous), estimate
