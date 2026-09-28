from datetime import date, datetime, time

from sqlmodel import Session, col, func, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.exceptions import ResourceDoesNotExistError
from bx_sch_4_nbs.database.models import BookedSlot, ScheduleException
from bx_sch_4_nbs.helpers.common import to_utc


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
