import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlmodel import Session, col, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.models import Appointment, BookedSlot, PublishedMonth, ScheduleException
from bx_sch_4_nbs.database.queries import day_slots
from bx_sch_4_nbs.database.types import AppointmentStatus, NailSize
from bx_sch_4_nbs.helpers.common import to_studio_time, to_utc, utc_now

type ExceptionMap = dict[tuple[date, time | None], bool]
type BusyPeriod = tuple[datetime, datetime]

# The same as schedule.ACTIVE_STATUSES (not imported, to keep this module free of schedule).
ACTIVE_STATUSES = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)
# No appointment lasts longer than this (the duration field caps at 600 minutes).
LONGEST_APPOINTMENT = timedelta(hours=10)


def is_open_for_clients(day: date, slot_time: time, exceptions: ExceptionMap) -> bool:
    # The weekly rule (settings.open_weekdays: Tuesday to Friday) unless the studio changed that day or slot,
    # Mondays included: closed by default, open when she opens them.
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


def appointment_end(appointment: Appointment) -> datetime:
    # The same as schedule.duration_minutes: the recorded duration, otherwise the service's usual one.
    minutes = appointment.duration_minutes or settings.service_durations_minutes[appointment.service]
    return appointment.scheduled_at + timedelta(minutes=minutes)


def active_appointments_between(session: Session, start: datetime, end: datetime) -> list[Appointment]:
    """Active appointments that may be running at some point between start and end."""
    return list(
        session.exec(
            select(Appointment).where(
                col(Appointment.status).in_(ACTIVE_STATUSES),
                col(Appointment.scheduled_at) > start - LONGEST_APPOINTMENT,
                col(Appointment.scheduled_at) < end,
            )
        ).all()
    )


def get_busy_periods(session: Session, start: datetime, end: datetime) -> list[BusyPeriod]:
    return [(a.scheduled_at, appointment_end(a)) for a in active_appointments_between(session, start, end)]


def overlaps_busy_period(slot_at: datetime, busy: list[BusyPeriod]) -> bool:
    """
    A client booking at slot_at would still be running when an appointment starts, or would start
    while one is running. E.g. 11:00 closes 10:00; 15:00 closes 14:00 and 17:00.
    """
    slot_end = slot_at + timedelta(minutes=settings.client_slot_minutes)
    return any(start < slot_end and slot_at < end for start, end in busy)


def available_slots(
    session: Session,
    year: int,
    month: int,
    nail_size: NailSize | None = None,
    require_published: bool = True,
    now: datetime | None = None,
) -> list[datetime]:
    if not now:
        now = utc_now()

    if require_published and not is_month_published(session, year, month):
        return []

    days_in_month = calendar.monthrange(year, month)[1]
    first_day = date(year, month, 1)
    last_day = date(year, month, days_in_month)

    exceptions = get_exceptions(session, first_day, last_day)
    custom_slots = day_slots.slots_by_day(session, first_day, last_day)
    month_start = to_utc(datetime.combine(first_day, time.min))
    month_end = to_utc(datetime.combine(last_day + timedelta(days=1), time.min))
    booked = get_booked_slots(session, start=month_start, end=month_end)
    busy = get_busy_periods(session, month_start, month_end + timedelta(minutes=settings.client_slot_minutes))

    result = []
    for day_number in range(days_in_month):
        day = first_day + timedelta(days=day_number)
        slots = day_slots.slots_of(day, custom_slots)
        for slot_time in slots:
            if not is_open_for_clients(day, slot_time, exceptions):
                continue
            if not is_slot_allowed_for_size(slot_time, nail_size, slots):
                continue
            slot_at = to_utc(datetime.combine(day, slot_time))
            if slot_at in booked or slot_at <= now + timedelta(hours=settings.min_booking_advance_hours):
                continue
            if overlaps_busy_period(slot_at, busy):
                continue
            result.append(slot_at)

    return result


def is_slot_allowed_for_size(slot_time: time, nail_size: NailSize | None, day_slots_: list[time]) -> bool:
    """Long nails take more time: they only go in the first or the last slot of the day."""
    if nail_size in settings.restricted_nail_sizes:
        return slot_time in (min(day_slots_), max(day_slots_))
    return True


def is_slot_available(session: Session, slot_at: datetime, nail_size: NailSize | None) -> bool:
    studio_time = to_studio_time(slot_at)
    return slot_at in available_slots(session, studio_time.year, studio_time.month, nail_size)


@dataclass
class AgendaSlot:
    time: time
    is_open: bool
    is_booked: bool
    # Not booked itself, but too close to an appointment: clients cannot book it.
    is_overlapped: bool


@dataclass
class AgendaDayInfo:
    slots: list[AgendaSlot]
    custom_times: bool


def month_agenda(session: Session, year: int, month: int) -> dict[date, AgendaDayInfo]:
    """Every slot of a month as the clients see it: open or closed, booked or free."""
    days_in_month = calendar.monthrange(year, month)[1]
    first_day = date(year, month, 1)
    last_day = date(year, month, days_in_month)

    exceptions = get_exceptions(session, first_day, last_day)
    custom_slots = day_slots.slots_by_day(session, first_day, last_day)
    month_start = to_utc(datetime.combine(first_day, time.min))
    month_end = to_utc(datetime.combine(last_day + timedelta(days=1), time.min))
    booked = get_booked_slots(session, start=month_start, end=month_end)
    busy = get_busy_periods(session, month_start, month_end + timedelta(minutes=settings.client_slot_minutes))

    def agenda_slot(day: date, slot_time: time) -> AgendaSlot:
        slot_at = to_utc(datetime.combine(day, slot_time))
        is_booked = slot_at in booked
        return AgendaSlot(
            time=slot_time,
            is_open=is_open_for_clients(day, slot_time, exceptions),
            is_booked=is_booked,
            is_overlapped=not is_booked and overlaps_busy_period(slot_at, busy),
        )

    agenda: dict[date, AgendaDayInfo] = {}
    for day_number in range(days_in_month):
        day = first_day + timedelta(days=day_number)
        agenda[day] = AgendaDayInfo(
            slots=[agenda_slot(day, slot_time) for slot_time in day_slots.slots_of(day, custom_slots)],
            custom_times=day in custom_slots,
        )
    return agenda


def overlapping_appointments(
    session: Session, scheduled_at: datetime, minutes: int, exclude_id: int | None = None
) -> list[Appointment]:
    """
    For the studio: the active appointments that would be running at the same time as a new one.
    The exact same time is left out: that is already refused as booked.
    """
    end = scheduled_at + timedelta(minutes=minutes)
    return sorted(
        (
            appointment
            for appointment in active_appointments_between(session, scheduled_at, end)
            if appointment.id != exclude_id
            and appointment.scheduled_at != scheduled_at
            and scheduled_at < appointment_end(appointment)
        ),
        key=lambda appointment: appointment.scheduled_at,
    )
