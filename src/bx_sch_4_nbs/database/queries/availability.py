import calendar
from datetime import date, datetime, time, timedelta

from sqlmodel import Session, col, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.models import BookedSlot, PublishedMonth, ScheduleException
from bx_sch_4_nbs.helpers.common import to_utc, utc_now

MONDAY = 0

type ExceptionMap = dict[tuple[date, time | None], bool]


def is_open_for_clients(day: date, slot_time: time, exceptions: ExceptionMap) -> bool:
    if day.weekday() == MONDAY:
        return False

    day_open = exceptions.get((day, None), day.weekday() in settings.open_weekdays)
    return exceptions.get((day, slot_time), day_open)


def is_month_published(session: Session, year: int, month: int) -> bool:
    return session.get(PublishedMonth, (year, month)) is not None


def get_exceptions(session: Session, first_day: date, last_day: date) -> ExceptionMap:
    rows = session.exec(select(ScheduleException).where(col(ScheduleException.day).between(first_day, last_day))).all()
    return {(row.day, row.slot_time): row.is_open for row in rows}


def get_booked_slots(session: Session, start: datetime, end: datetime) -> set[datetime]:
    rows = session.exec(
        select(BookedSlot.slot_at).where(col(BookedSlot.slot_at) >= start, col(BookedSlot.slot_at) < end)
    ).all()
    return set(rows)


def available_slots(session: Session, year: int, month: int) -> list[datetime]:
    if not is_month_published(session, year, month):
        return []

    days_in_month = calendar.monthrange(year, month)[1]
    first_day = date(year, month, 1)
    last_day = date(year, month, days_in_month)

    exceptions = get_exceptions(session, first_day, last_day)
    booked = get_booked_slots(
        session,
        start=to_utc(datetime.combine(first_day, time.min)),
        end=to_utc(datetime.combine(last_day + timedelta(days=1), time.min)),
    )
    now = utc_now()

    result = []
    for day_number in range(days_in_month):
        day = first_day + timedelta(days=day_number)
        for slot_time in settings.appointment_slots:
            if not is_open_for_clients(day, slot_time, exceptions):
                continue
            slot_at = to_utc(datetime.combine(day, slot_time))
            if slot_at in booked or slot_at <= now:
                continue
            result.append(slot_at)

    return result
