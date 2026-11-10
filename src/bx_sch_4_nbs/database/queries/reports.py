from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlmodel import Session, col, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.models import Appointment
from bx_sch_4_nbs.database.queries.expenses import list_expenses
from bx_sch_4_nbs.database.queries.schedule import duration_minutes
from bx_sch_4_nbs.database.types import AppointmentStatus, CancellationReason, ExpenseCategory, Service, TradeItem
from bx_sch_4_nbs.helpers.common import to_studio_time, to_utc

# Cancellations where the studio keeps the deposit (as the policies say).
KEPT_DEPOSIT_REASONS = (CancellationReason.CLIENT_LATE, CancellationReason.NOT_CONFIRMED)


@dataclass
class ServiceTotals:
    completed: int = 0
    worked_minutes: int = 0
    revenue: Decimal = Decimal(0)


CENT = Decimal("0.01")


def _per(amount: Decimal, count: int) -> Decimal | None:
    """amount / count in euros and cents; None when there is nothing to divide by (no "0 €" that means nothing)."""
    return (amount / count).quantize(CENT) if count else None


@dataclass
class PeriodReport:
    """The numbers of a period (a month, or the whole year)."""

    completed: int = 0
    worked_minutes: int = 0
    services_revenue: Decimal = Decimal(0)
    kept_deposits: int = 0
    no_shows: int = 0
    cancellations: int = 0
    by_service: dict[Service, ServiceTotals] = field(default_factory=dict)
    expenses_by_category: dict[ExpenseCategory, Decimal] = field(default_factory=dict)
    # Trades are apart: no money, so they stay out of completed / worked_minutes ("per hour worked").
    trades: int = 0
    trade_minutes: int = 0
    trades_by_item: dict[TradeItem, ServiceTotals] = field(default_factory=dict)
    # Who was served and on which days (Lisbon dates), from the completed paid appointments.
    # Sets, not counts: a client who came twice is one client, and two appointments on one day are one day.
    # That is also why the year cannot just add up its months: it joins the sets.
    client_ids: set[int] = field(default_factory=set)
    days: set[date] = field(default_factory=set)

    @property
    def clients(self) -> int:
        return len(self.client_ids)

    @property
    def days_worked(self) -> int:
        return len(self.days)

    @property
    def revenue_per_hour(self) -> Decimal | None:
        """Income from services per hour worked (kept deposits need no work, so they stay out)."""
        if not self.worked_minutes:
            return None
        return (self.services_revenue * 60 / self.worked_minutes).quantize(CENT)

    @property
    def average_per_client(self) -> Decimal | None:
        """What each client paid on average for her services in the period."""
        return _per(self.services_revenue, self.clients)

    @property
    def average_per_day(self) -> Decimal | None:
        return _per(self.services_revenue, self.days_worked)

    @property
    def cost_per_client(self) -> Decimal | None:
        """The period's expenses split among the clients served."""
        return _per(self.expenses, self.clients)

    @property
    def profit_per_client(self) -> Decimal | None:
        """What is left of each client after her share of the expenses (e.g. 40 paid - 12 of material = 28)."""
        if self.average_per_client is None or self.cost_per_client is None:
            return None
        return self.average_per_client - self.cost_per_client

    @property
    def kept_deposits_revenue(self) -> Decimal:
        return settings.deposit_amount * self.kept_deposits

    @property
    def total_revenue(self) -> Decimal:
        return self.services_revenue + self.kept_deposits_revenue

    @property
    def expenses(self) -> Decimal:
        return sum(self.expenses_by_category.values(), Decimal(0))

    @property
    def profit(self) -> Decimal:
        return self.total_revenue - self.expenses


@dataclass
class MonthReport(PeriodReport):
    month: int = 0


def whole_year(months: list[MonthReport]) -> PeriodReport:
    """The year's totals: sums of the months, and the clients and days joined (not added up)."""
    year = PeriodReport()
    for month in months:
        year.completed += month.completed
        year.worked_minutes += month.worked_minutes
        year.services_revenue += month.services_revenue
        year.kept_deposits += month.kept_deposits
        year.no_shows += month.no_shows
        year.cancellations += month.cancellations
        year.trades += month.trades
        year.trade_minutes += month.trade_minutes
        year.client_ids |= month.client_ids
        year.days |= month.days
        for category, amount in month.expenses_by_category.items():
            year.expenses_by_category[category] = year.expenses_by_category.get(category, Decimal(0)) + amount
    return year


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
        local_time = to_studio_time(appointment.scheduled_at)
        report = months[local_time.month - 1]

        if appointment.status == AppointmentStatus.COMPLETED and appointment.service == Service.TRADING:
            minutes = duration_minutes(appointment)
            report.trades += 1
            report.trade_minutes += minutes
            item = report.trades_by_item.setdefault(appointment.trade_item or TradeItem.NAILS, ServiceTotals())
            item.completed += 1
            item.worked_minutes += minutes
        elif appointment.status == AppointmentStatus.COMPLETED:
            minutes = duration_minutes(appointment)
            price = appointment.final_price if appointment.final_price is not None else appointment.estimated_price
            report.completed += 1
            report.worked_minutes += minutes
            report.services_revenue += price
            report.client_ids.add(appointment.user_id)
            report.days.add(local_time.date())
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

    # Expenses already have a Lisbon date: no conversion needed.
    for expense in list_expenses(session, date(year, 1, 1), date(year, 12, 31)):
        totals = months[expense.day.month - 1].expenses_by_category
        totals[expense.category] = totals.get(expense.category, Decimal(0)) + expense.amount

    return months
