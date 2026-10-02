from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.exceptions import (
    AppointmentNotActiveError,
    CancellationNotAllowedError,
    DuplicateResourceError,
    ResourceDoesNotExistError,
)
from bx_sch_4_nbs.database.models import (
    Appointment,
    BookedSlot,
    ScheduleException,
    User,
)
from bx_sch_4_nbs.database.types import (
    AppointmentStatus,
    CancellationReason,
    NailArtLevel,
    NailSize,
    Service,
)
from bx_sch_4_nbs.helpers.common import to_utc, utc_now

ACTIVE_STATUSES = (
    AppointmentStatus.SCHEDULED,
    AppointmentStatus.CONFIRMED,
)
REFUNDABLE_REASONS = (CancellationReason.CLIENT_EARLY, CancellationReason.BY_STUDIO)


def apply_cancellation(
    session: Session,
    appointment: Appointment,
    reason: CancellationReason,
    cancelled_by: int | None,
    now: datetime,
) -> None:
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = now
    appointment.cancelled_by = cancelled_by
    appointment.cancellation_reason = reason
    session.add(appointment)

    booked_slot = session.get(BookedSlot, appointment.scheduled_at)
    if booked_slot is not None:
        session.delete(booked_slot)

    session.flush()


def list_exceptions(session: Session, first_day: date, last_day: date) -> list[ScheduleException]:
    return list(
        session.exec(
            select(ScheduleException)
            .where(col(ScheduleException.day).between(first_day, last_day))
            .order_by(col(ScheduleException.day), col(ScheduleException.slot_time))
        ).all()
    )


def set_exception(session: Session, day: date, slot_time: time | None, is_open: bool) -> ScheduleException:
    entry = session.exec(
        select(ScheduleException).where(ScheduleException.day == day, ScheduleException.slot_time == slot_time)
    ).first()

    if entry is None:
        entry = ScheduleException(day=day, slot_time=slot_time, is_open=is_open)
    else:
        entry.is_open = is_open

    session.add(entry)
    session.flush()
    return entry


def delete_exception(session: Session, exception_id: int) -> None:
    entry = session.get(ScheduleException, exception_id)
    if entry is None:
        raise ResourceDoesNotExistError(f"Schedule exception {exception_id} does not exist.")
    session.delete(entry)


def count_booked_slots(session: Session, day: date, slot_time: time | None) -> int:
    slot_times = [slot_time] if slot_time is not None else settings.appointment_slots
    instants = [to_utc(datetime.combine(day, t)) for t in slot_times]
    return session.exec(select(func.count()).select_from(BookedSlot).where(col(BookedSlot.slot_at).in_(instants))).one()


def is_refund_due(appointment: Appointment) -> bool:
    return appointment.deposit_paid_at is not None and appointment.cancellation_reason in REFUNDABLE_REASONS


def cancel_appointment(session: Session, appointment_id: int, user_id: int, accept_deposit_loss: bool) -> Appointment:
    appointment = session.get(Appointment, appointment_id)

    if appointment is None or appointment.user_id != user_id:
        raise ResourceDoesNotExistError(f"Appointment {appointment_id} does not exist.")

    if appointment.status not in ACTIVE_STATUSES:
        raise CancellationNotAllowedError("Only scheduled or confirmed appointments can be cancelled.")

    now = utc_now()
    if appointment.scheduled_at <= now:
        raise CancellationNotAllowedError("This appointment has already started and cannot be cancelled.")

    is_early = appointment.scheduled_at - now > timedelta(hours=settings.free_cancellation_hours)
    reason = CancellationReason.CLIENT_EARLY if is_early else CancellationReason.CLIENT_LATE

    if reason == CancellationReason.CLIENT_LATE and not accept_deposit_loss:
        raise CancellationNotAllowedError(
            f"Cancelling less than {settings.free_cancellation_hours} hours before the appointment means "
            "the deposit will not be refunded. Send accept_deposit_loss: true to confirm."
        )

    apply_cancellation(session, appointment, reason, user_id, now)
    return appointment


def auto_cancel_appointment(session: Session, appointment: Appointment, now: datetime) -> None:
    apply_cancellation(session, appointment, CancellationReason.NOT_CONFIRMED, None, now)


def mark_reminder_sent(session: Session, appointment: Appointment, now: datetime) -> None:
    appointment.reminder_sent_at = now
    session.add(appointment)
    session.flush()


def create_appointment(
    session: Session,
    *,
    user_id: int,
    scheduled_at: datetime,
    service: Service,
    nail_size: NailSize | None,
    nail_art_level: NailArtLevel | None,
    broken_nails: int,
    has_other_professional_nails: bool,
    estimated_price: Decimal,
    policy_id: int,
) -> Appointment:
    appointment = Appointment(
        user_id=user_id,
        scheduled_at=scheduled_at,
        status=AppointmentStatus.SCHEDULED,
        service=service,
        nail_size=nail_size,
        nail_art_level=nail_art_level,
        broken_nails=broken_nails,
        has_other_professional_nails=has_other_professional_nails,
        estimated_price=estimated_price,
        policy_id=policy_id,
        policies_accepted_at=utc_now(),
    )
    session.add(appointment)
    session.flush()

    if appointment.id is None:
        raise RuntimeError("Appointment was not assigned an id.")

    session.add(BookedSlot(slot_at=scheduled_at, appointment_id=appointment.id))
    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateResourceError("This slot has just been booked. Please choose another one.") from error

    return appointment


def appointments_needing_reminder(session: Session, now: datetime) -> list[Appointment]:

    appointments = list(
        session.exec(
            select(Appointment).where(
                col(Appointment.status).in_(ACTIVE_STATUSES),
                col(Appointment.reminder_sent_at).is_(None),
                col(Appointment.scheduled_at) > now,
                col(Appointment.scheduled_at) <= now + timedelta(hours=settings.reminder_hours_before),
            )
        ).all()
    )

    return appointments


def appointments_to_auto_cancel(session: Session, now: datetime) -> list[Appointment]:
    appointments = list(
        session.exec(
            select(Appointment).where(
                col(Appointment.status).in_(ACTIVE_STATUSES),
                col(Appointment.attendance_confirmed_at).is_(None),
                col(Appointment.reminder_sent_at).is_not(None),
                col(Appointment.scheduled_at) > now,
                col(Appointment.scheduled_at) <= now + timedelta(hours=settings.confirmation_deadline_hours_before),
            )
        ).all()
    )

    return appointments


def confirm_attendance(session: Session, appointment_id: int, now: datetime) -> Appointment:
    appointment = session.get(Appointment, appointment_id)

    if appointment is None:
        raise ResourceDoesNotExistError("Appointment does not exist.")

    if appointment.status not in ACTIVE_STATUSES:
        raise AppointmentNotActiveError(
            "This appointment is no longer active (it was cancelled or already happened). Please contact NailsByScooby."
        )

    if appointment.attendance_confirmed_at is not None:
        return appointment

    appointment.attendance_confirmed_at = now
    session.add(appointment)
    session.flush()

    return appointment


def list_appointments(
    session: Session,
    first_day: date,
    last_day: date,
    status: AppointmentStatus | None = None,
) -> list[tuple[Appointment, User]]:

    start = to_utc(datetime.combine(first_day, time.min))
    end = to_utc(datetime.combine(last_day + timedelta(days=1), time.min))

    statement = (
        select(Appointment, User)
        .join(User, col(Appointment.user_id) == col(User.id))
        .where(
            col(Appointment.scheduled_at) >= start,
            col(Appointment.scheduled_at) < end,
        )
        .order_by(col(Appointment.scheduled_at))
    )

    if status is not None:
        statement = statement.where(col(Appointment.status) == status)

    result = list(session.exec(statement).all())

    return result


def is_deposit_overdue(appointment: Appointment, now: datetime) -> bool:
    scheduled = AppointmentStatus.SCHEDULED
    limit = now - timedelta(days=settings.deposit_overdue_days)

    if not appointment.created_at:
        return False

    return appointment.status == scheduled and appointment.created_at < limit
