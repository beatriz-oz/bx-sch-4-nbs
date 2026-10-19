from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlmodel import Session, col, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.models import Appointment
from bx_sch_4_nbs.database.queries.schedule import duration_minutes
from bx_sch_4_nbs.database.types import AppointmentStatus, CancellationReason, Service
from bx_sch_4_nbs.helpers.common import to_studio_time, to_utc

# Cancellations where the studio keeps the deposit (as the policies say).
KEPT_DEPOSIT_REASONS = (CancellationReason.CLIENT_LATE, CancellationReason.NOT_CONFIRMED)


@dataclass
class ServiceTotals:
    completed: int = 0
    worked_minutes: int = 0
    revenue: Decimal = Decimal(0)


@dataclass
class MonthReport:
    month: int
    completed: int = 0
    worked_minutes: int = 0
    services_revenue: Decimal = Decimal(0)
    kept_deposits: int = 0
    no_shows: int = 0
    cancellations: int = 0
    by_service: dict[Service, ServiceTotals] = field(default_factory=dict)

    @property
    def kept_deposits_revenue(self) -> Decimal:
        return settings.deposit_amount * self.kept_deposits

    @property
    def total_revenue(self) -> Decimal:
        return self.services_revenue + self.kept_deposits_revenue


def keeps_deposit(appointment: Appointment) -> bool:
    """A paid deposit the studio keeps: a no-show, or a late / unconfirmed cancellation."""
    if appointment.deposit_paid_at is None:
        return False
    if appointment.status == AppointmentStatus.NO_SHOW:
        return True
    return appointment.status == AppointmentStatus.CANCELLED and appointment.cancellation_reason in KEPT_DEPOSIT_REASONS


def year_report(session: Session, year: int) -> list[MonthReport]:
    """
    The 12 months of a year in the studio's calendar (Lisbon). An appointment counts in the
    month of its date, in Lisbon time: 00:30 on 1 November in Lisbon is still 31 October in UTC.
    There are few appointments a year, so they are grouped here rather than in SQL.
    """
    start = to_utc(datetime(year, 1, 1))  # noqa: DTZ001 - a Lisbon wall-clock time, converted to UTC
    end = to_utc(datetime(year + 1, 1, 1))  # noqa: DTZ001
    appointments = session.exec(
        select(Appointment).where(col(Appointment.scheduled_at) >= start, col(Appointment.scheduled_at) < end)
    ).all()

    months = [MonthReport(month=number) for number in range(1, 13)]
    for appointment in appointments:
        report = months[to_studio_time(appointment.scheduled_at).month - 1]

        if appointment.status == AppointmentStatus.COMPLETED:
            minutes = duration_minutes(appointment)
            price = appointment.final_price if appointment.final_price is not None else appointment.estimated_price
            report.completed += 1
            report.worked_minutes += minutes
            report.services_revenue += price
            totals = report.by_service.setdefault(appointment.service, ServiceTotals())
            totals.completed += 1
            totals.worked_minutes += minutes
            totals.revenue += price
        elif appointment.status == AppointmentStatus.NO_SHOW:
            report.no_shows += 1
        elif appointment.status == AppointmentStatus.CANCELLED:
            report.cancellations += 1

        if keeps_deposit(appointment):
            report.kept_deposits += 1

    return months
