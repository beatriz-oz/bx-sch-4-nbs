from datetime import date, time

from sqlmodel import Session, col, delete, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.models import DaySlot


def slots_by_day(session: Session, first_day: date, last_day: date) -> dict[date, list[time]]:
    """The days in the period that have their own slots (the others use the default)."""
    rows = session.exec(
        select(DaySlot).where(col(DaySlot.day).between(first_day, last_day)).order_by(col(DaySlot.slot_time))
    ).all()
    custom: dict[date, list[time]] = {}
    for row in rows:
        custom.setdefault(row.day, []).append(row.slot_time)
    return custom


def slots_of(day: date, custom: dict[date, list[time]]) -> list[time]:
    return custom.get(day, settings.appointment_slots)


def slots_for_day(session: Session, day: date) -> list[time]:
    return slots_of(day, slots_by_day(session, day, day))


def set_day_slots(session: Session, day: date, slot_times: list[time]) -> list[time]:
    """Replaces the slots of a day. An empty list goes back to the default slots."""
    session.exec(delete(DaySlot).where(col(DaySlot.day) == day))
    for slot_time in sorted(set(slot_times)):
        session.add(DaySlot(day=day, slot_time=slot_time))
    session.flush()
    return slots_for_day(session, day)
