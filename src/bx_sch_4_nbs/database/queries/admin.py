from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, or_
from sqlmodel import Session, col, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.exceptions import (
    AppointmentNotActiveError,
    AppointmentTooEarlyError,
    CancellationNotAllowedError,
    ResourceDoesNotExistError,
)
from bx_sch_4_nbs.database.models import Appointment, User
from bx_sch_4_nbs.database.queries import prices, schedule
from bx_sch_4_nbs.database.types import (
    AppointmentStatus,
    CancellationReason,
    NailArtLevel,
    NailSize,
    Service,
    UserRole,
)
from bx_sch_4_nbs.helpers.security import hash_email, hash_phone, normalize_phone


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


def cancel_appointment_by_studio(
    session: Session,
    appointment_id: int,
    admin_id: int,
    now: datetime,
) -> tuple[Appointment, User]:
    appointment = session.get(Appointment, appointment_id)

    if not appointment:
        raise ResourceDoesNotExistError("The appointment does not exist")

    user = session.get(User, appointment.user_id)
    if not user:
        raise ResourceDoesNotExistError("The user does not exist")

    if appointment.status not in schedule.ACTIVE_STATUSES:
        raise AppointmentNotActiveError(
            f"Appointment cannot be cancelled, the current status is: {appointment.status.value}"
        )

    if appointment.scheduled_at <= now:
        raise CancellationNotAllowedError(
            "This appointment cannot be cancelled. Please, define this appointment as completed or no_show"
        )

    schedule.apply_cancellation(
        session,
        appointment,
        reason=CancellationReason.BY_STUDIO,
        cancelled_by=admin_id,
        now=now,
    )

    return appointment, user


def _get_appointment_to_finish(session: Session, appointment_id: int, now: datetime) -> tuple[Appointment, User]:
    appointment = session.get(Appointment, appointment_id)

    if not appointment:
        raise ResourceDoesNotExistError("The appointment does not exist")

    user = session.get(User, appointment.user_id)
    if not user:
        raise ResourceDoesNotExistError("The user does not exist")

    if appointment.status not in schedule.ACTIVE_STATUSES:
        raise AppointmentNotActiveError(
            f"Appointment cannot be finished, the current status is: {appointment.status.value}"
        )

    if appointment.scheduled_at > now:
        raise AppointmentTooEarlyError("This appointment has not started yet, so it cannot be finished")

    return appointment, user


def complete_appointment(
    session: Session, appointment_id: int, final_price: Decimal, duration_minutes: int | None, now: datetime
) -> tuple[Appointment, User]:
    appointment, user = _get_appointment_to_finish(session, appointment_id, now)

    appointment.status = AppointmentStatus.COMPLETED
    appointment.final_price = final_price
    appointment.duration_minutes = duration_minutes
    session.add(appointment)
    session.flush()

    return appointment, user


def mark_no_show(session: Session, appointment_id: int, now: datetime) -> tuple[Appointment, User]:
    appointment, user = _get_appointment_to_finish(session, appointment_id, now)

    appointment.status = AppointmentStatus.NO_SHOW
    session.add(appointment)
    session.flush()

    return appointment, user


def estimate_final_price(
    session: Session,
    appointment_id: int,
    *,
    nail_size: NailSize | None,
    nail_art_level: NailArtLevel | None,
    broken_nails: int | None,
    extra_charms: int,
    complete_removal: bool,
) -> tuple[Service, Decimal]:
    appointment = session.get(Appointment, appointment_id)

    if not appointment:
        raise ResourceDoesNotExistError("The appointment does not exist")

    if appointment.service == Service.OTHER:
        return appointment.service, appointment.estimated_price

    # What was not changed in the form keeps the value chosen when booking.
    price = prices.calculate_price(
        session,
        service=appointment.service,
        nail_size=nail_size or appointment.nail_size,
        nail_art_level=nail_art_level or appointment.nail_art_level,
        broken_nails=appointment.broken_nails if broken_nails is None else broken_nails,
        extra_charms=extra_charms,
        complete_removal=complete_removal,
    )

    return appointment.service, price


def get_client(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None or user.role != UserRole.USER:
        raise ResourceDoesNotExistError("The client does not exist")
    return user


def is_within_reminder_window(scheduled_at: datetime, now: datetime) -> bool:
    # Also true for the past: those bookings get no reminder and no welcome email.
    return scheduled_at <= now + timedelta(hours=settings.reminder_hours_before)


def book_appointment_by_studio(
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
    notes: str | None,
    policy_id: int,
    now: datetime,
) -> Appointment:
    # A squeeze-in was just agreed with the client, so attendance is already confirmed.
    is_squeeze_in = now < scheduled_at and is_within_reminder_window(scheduled_at, now)

    return schedule.create_appointment(
        session,
        user_id=user_id,
        scheduled_at=scheduled_at,
        service=service,
        nail_size=nail_size,
        nail_art_level=nail_art_level,
        broken_nails=broken_nails,
        has_other_professional_nails=has_other_professional_nails,
        estimated_price=estimated_price,
        policy_id=policy_id,
        policies_accepted_at=None,
        notes=notes,
        attendance_confirmed_at=now if is_squeeze_in else None,
    )


def search_clients(session: Session, search: str, limit: int) -> list[User]:
    term = search.strip().lstrip("@")
    conditions = [
        col(User.name).contains(term),
        col(User.last_name).contains(term),
        col(User.instagram).contains(term.lower()),
        col(User.email_hash) == hash_email(term),
    ]
    # Phone and email are encrypted, so they can only be found by their exact hash.
    try:
        conditions.append(col(User.phone_hash) == hash_phone(normalize_phone(term)))
    except ValueError:
        pass

    return list(
        session.exec(
            select(User)
            .where(User.role == UserRole.USER, or_(*conditions))
            .order_by(col(User.name), col(User.last_name))
            .limit(limit)
        ).all()
    )


# --- payments: pending deposits, refunds, cancellations ---

RECENT_CANCELLATIONS_DAYS = 30


def mark_deposit_refunded(session: Session, appointment_id: int, now: datetime) -> tuple[Appointment, User]:
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise ResourceDoesNotExistError("The appointment does not exist")

    user = session.get(User, appointment.user_id)
    if not user:
        raise ResourceDoesNotExistError("The user does not exist")

    # Already marked: nothing to do (a double click must not change the date).
    if appointment.deposit_refunded_at is not None:
        return appointment, user

    if not schedule.is_refund_due(appointment):
        raise AppointmentNotActiveError("No refund is due for this appointment.")

    appointment.deposit_refunded_at = now
    session.add(appointment)
    session.flush()
    return appointment, user


def pending_deposits(session: Session, now: datetime) -> list[tuple[Appointment, User]]:
    """Upcoming appointments still waiting for the deposit (OTHER never needs one)."""
    return list(
        session.exec(
            select(Appointment, User)
            .join(User, col(Appointment.user_id) == col(User.id))
            .where(
                Appointment.status == AppointmentStatus.SCHEDULED,
                Appointment.service != Service.OTHER,
                col(Appointment.scheduled_at) > now,
            )
            .order_by(col(Appointment.scheduled_at))
        ).all()
    )


def refunds_due(session: Session) -> list[tuple[Appointment, User]]:
    """Cancelled appointments whose paid deposit must still be given back, the oldest first."""
    return list(
        session.exec(
            select(Appointment, User)
            .join(User, col(Appointment.user_id) == col(User.id))
            .where(
                Appointment.status == AppointmentStatus.CANCELLED,
                col(Appointment.deposit_paid_at).is_not(None),
                col(Appointment.cancellation_reason).in_(schedule.REFUNDABLE_REASONS),
                col(Appointment.deposit_refunded_at).is_(None),
            )
            .order_by(col(Appointment.cancelled_at))
        ).all()
    )


def recent_cancellations(session: Session, now: datetime) -> list[tuple[Appointment, User]]:
    since = now - timedelta(days=RECENT_CANCELLATIONS_DAYS)
    return list(
        session.exec(
            select(Appointment, User)
            .join(User, col(Appointment.user_id) == col(User.id))
            .where(Appointment.status == AppointmentStatus.CANCELLED, col(Appointment.cancelled_at) >= since)
            .order_by(col(Appointment.cancelled_at).desc())
        ).all()
    )


# --- clients ---


def clients_overview(
    session: Session, *, registered: bool, now: datetime
) -> list[tuple[User, int, datetime | None, datetime | None]]:
    """
    The clients with password (registered) or without (pending), each with the number of
    completed visits, the last visit and the next appointment. One query with LEFT JOIN,
    so clients who never booked are listed too.
    """
    completed = col(Appointment.status) == AppointmentStatus.COMPLETED
    upcoming = col(Appointment.status).in_(schedule.ACTIVE_STATUSES) & (col(Appointment.scheduled_at) > now)

    return list(
        session.exec(
            select(
                User,
                func.count(case((completed, col(Appointment.id)))),
                func.max(case((completed, col(Appointment.scheduled_at)))),
                func.min(case((upcoming, col(Appointment.scheduled_at)))),
            )
            .join(Appointment, col(Appointment.user_id) == col(User.id), isouter=True)
            .where(col(User.role) == UserRole.USER, col(User.is_active).is_(registered))
            .group_by(col(User.id))
            .order_by(col(User.name), col(User.last_name))
        ).all()
    )
