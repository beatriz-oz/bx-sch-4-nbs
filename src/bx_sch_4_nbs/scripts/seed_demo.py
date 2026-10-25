"""
Demo data to show the system: clients, ~3 months of history and ~5 weeks of agenda,
plus the studio's expenses of those months.

    uv run python -m bx_sch_4_nbs.scripts.seed_demo          # (re)creates the demo data
    uv run python -m bx_sch_4_nbs.scripts.seed_demo --reset  # only removes it

Everything is written straight to the database: no email is sent. The demo clients are
recognised by their Instagram handles (DEMO_CLIENTS), and the demo expenses by their
descriptions (DEMO_EXPENSES), so removing them never touches other data.
The dates are relative to today, so the demo always looks current.
"""

import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlmodel import Session, col, delete, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import (
    Appointment,
    BookedSlot,
    Expense,
    Policy,
    PreApprovedInstagram,
    PublishedMonth,
    User,
)
from bx_sch_4_nbs.database.queries.prices import calculate_price
from bx_sch_4_nbs.database.types import (
    AppointmentStatus,
    CancellationReason,
    ExpenseCategory,
    NailArtLevel,
    NailSize,
    Service,
)
from bx_sch_4_nbs.helpers.common import to_studio_time, to_utc, utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_password, hash_phone

# (name, last name, instagram, phone, registered = has a password)
DEMO_CLIENTS = [
    ("Ana", "Ferreira", "ana.ferreira.nails", "+351912345601", True),
    ("Beatriz", "Santos", "bia.santos", "+351912345602", True),
    ("Carolina", "Mendes", "carol.mendes", "+351912345603", True),
    ("Daniela", "Costa", "dani.costa", "+351912345604", True),
    ("Eduarda", "Rocha", "duda.rocha", "+5511987650005", True),
    ("Filipa", "Almeida", "filipa.almeida", "+351912345606", True),
    ("Gabriela", "Lima", "gabi.lima", "+5521987650007", True),
    ("Helena", "Sousa", "helena.sousa", "+351912345608", True),
    ("Inês", "Martins", "ines.martins", "+351912345609", True),
    ("Joana", "Pereira", "joana.pereira", "+351912345610", True),
    ("Larissa", "Oliveira", "lari.oliveira", "+5531987650011", True),
    ("Mariana", "Ribeiro", "mari.ribeiro", "+351912345612", False),
    ("Natália", "Gomes", "nati.gomes", "+5511987650013", False),
    ("Rita", "Carvalho", "rita.carvalho", "+351912345614", False),
    ("Sofia", "Lopes", "sofia.lopes", "+351912345615", False),
]
# Approved by the studio but not checked in yet.
DEMO_PRE_APPROVED = ["camila.duarte", "leonor.pinto", "vitoria.reis"]
DEMO_PASSWORD = "demo-password-123"

SLOTS = [time(10, 0), time(14, 0), time(17, 0)]
SIZES = [
    NailSize.SMALL,
    NailSize.MEDIUM,
    NailSize.MEDIUM,
    NailSize.LARGE,
    NailSize.LARGE,
    NailSize.XLARGE,
    NailSize.XXLARGE,
]
ART = [NailArtLevel.LEVEL_1, NailArtLevel.LEVEL_2, NailArtLevel.LEVEL_2, NailArtLevel.LEVEL_3]
SERVICES = [Service.APPLICATION] * 4 + [Service.MAINTENANCE] * 5 + [Service.REMOVAL] + [Service.OTHER]
HANDLES = [handle for _, _, handle, _, _ in DEMO_CLIENTS]

# (day of the month, description, category, amount): repeated every month of the demo.
DEMO_EXPENSES = [
    (3, "Renda do espaço (demo)", ExpenseCategory.BILLS, Decimal("250.00")),
    (8, "Géis e verniz (demo)", ExpenseCategory.PRODUCTS, Decimal("86.40")),
    (15, "Limas, algodão e luvas (demo)", ExpenseCategory.MATERIAL, Decimal("32.75")),
    (20, "Luz e internet (demo)", ExpenseCategory.BILLS, Decimal("54.90")),
    (24, "Charms e pedrinhas (demo)", ExpenseCategory.PRODUCTS, Decimal("18.60")),
]


def remove_demo(session: Session) -> None:
    users = session.exec(select(User).where(col(User.instagram).in_(HANDLES))).all()
    ids = [user.id for user in users]
    if ids:
        appointment_ids = session.exec(select(Appointment.id).where(col(Appointment.user_id).in_(ids))).all()
        session.exec(delete(BookedSlot).where(col(BookedSlot.appointment_id).in_(appointment_ids)))
        session.exec(delete(Appointment).where(col(Appointment.user_id).in_(ids)))
        session.exec(delete(User).where(col(User.id).in_(ids)))
    session.exec(delete(PreApprovedInstagram).where(col(PreApprovedInstagram.instagram).in_(DEMO_PRE_APPROVED)))
    session.exec(delete(Expense).where(col(Expense.description).in_([e[1] for e in DEMO_EXPENSES])))
    session.commit()
    print(f"Removed {len(ids)} demo clients and their appointments.")


def create_clients(session: Session, now: datetime) -> list[User]:
    password_hash = hash_password(DEMO_PASSWORD)
    clients = []
    for index, (name, last_name, handle, phone, registered) in enumerate(DEMO_CLIENTS):
        email = f"{handle.replace('.', '_')}@example.com"
        user = User(
            name=name,
            last_name=last_name,
            instagram=handle,
            email_encrypted=encrypt_email(email),
            email_hash=hash_email(email),
            phone_encrypted=encrypt_phone(phone),
            phone_hash=hash_phone(phone),
            password_hash=password_hash if registered else None,
            is_active=registered,
            email_verified=registered or index % 2 == 0,
            approved_at=now - timedelta(days=30) if registered or handle == "mari.ribeiro" else None,
            created_at=now - timedelta(days=150 - index * 7),
        )
        session.add(user)
        clients.append(user)
    for handle in DEMO_PRE_APPROVED:
        session.add(PreApprovedInstagram(instagram=handle))
    session.flush()
    return clients


def booking_details(rng: random.Random) -> tuple[Service, NailSize | None, NailArtLevel | None, int]:
    service = rng.choice(SERVICES)
    if service in (Service.REMOVAL, Service.OTHER):
        return service, None, None, 0
    return service, rng.choice(SIZES), rng.choice(ART), rng.choice([0, 0, 0, 1, 2])


def main() -> None:
    rng = random.Random(42)  # the same demo every time
    now = utc_now()
    today = to_studio_time(now).date()

    with Session(engine) as session:
        remove_demo(session)
        if "--reset" in sys.argv:
            return

        policy = session.exec(select(Policy).order_by(col(Policy.id).desc())).first()
        if policy is None or policy.id is None:
            raise SystemExit("Publish a booking policy first (admin → Policies).")

        clients = create_clients(session, now)
        taken = set(session.exec(select(BookedSlot.slot_at)).all())
        counts: dict[str, int] = {}

        # Every Tuesday–Friday from ~3 months ago to ~5 weeks ahead.
        for offset in range(-95, 36):
            day = today + timedelta(days=offset)
            if day.weekday() not in settings.open_weekdays:
                continue
            for slot in SLOTS:
                past = offset < 0
                if rng.random() > (0.75 if past else 0.5):
                    continue
                scheduled_at = to_utc(datetime.combine(day, slot))
                if scheduled_at in taken or (offset == 0 and scheduled_at < now):
                    continue

                service, size, art, broken = booking_details(rng)
                if size in settings.restricted_nail_sizes and slot not in (SLOTS[0], SLOTS[-1]):
                    size = NailSize.LARGE
                client = rng.choice(clients)
                if client.id is None:
                    raise RuntimeError("Client without id.")
                estimated = (
                    Decimal(rng.choice([5, 8, 15]))
                    if service == Service.OTHER
                    else calculate_price(
                        session, service=service, nail_size=size, nail_art_level=art, broken_nails=broken
                    )
                )
                booked = scheduled_at - timedelta(days=rng.randint(3, 25))
                appointment = Appointment(
                    user_id=client.id,
                    scheduled_at=scheduled_at,
                    status=AppointmentStatus.SCHEDULED,
                    service=service,
                    nail_size=size,
                    nail_art_level=art,
                    broken_nails=broken,
                    has_other_professional_nails=rng.random() < 0.08,
                    estimated_price=estimated,
                    policy_id=policy.id,
                    policies_accepted_at=booked,
                    created_at=min(booked, now),
                    notes="Repair of 1 broken nail" if service == Service.OTHER else None,
                )
                needs_deposit = service != Service.OTHER

                if past:
                    outcome = rng.random()
                    appointment.deposit_paid_at = booked + timedelta(days=1) if needs_deposit else None
                    appointment.reminder_sent_at = scheduled_at - timedelta(hours=24)
                    if outcome < 0.80:
                        appointment.status = AppointmentStatus.COMPLETED
                        appointment.attendance_confirmed_at = scheduled_at - timedelta(hours=20)
                        extras = Decimal("0.50") * rng.choice([0, 0, 2, 4, 6])
                        appointment.final_price = estimated + extras
                        expected = settings.service_durations_minutes[service]
                        appointment.duration_minutes = max(30, expected + rng.choice([-30, -15, 0, 0, 15, 30, 45]))
                    elif outcome < 0.86:
                        appointment.status = AppointmentStatus.NO_SHOW
                    else:
                        appointment.status = AppointmentStatus.CANCELLED
                        reason = rng.choice(list(CancellationReason))
                        appointment.cancellation_reason = reason
                        appointment.cancelled_at = scheduled_at - timedelta(
                            hours=72 if reason == CancellationReason.CLIENT_EARLY else 10
                        )
                        appointment.cancelled_by = (
                            client.id
                            if reason
                            in (
                                CancellationReason.CLIENT_EARLY,
                                CancellationReason.CLIENT_LATE,
                            )
                            else None
                        )
                        refundable = reason in (CancellationReason.CLIENT_EARLY, CancellationReason.BY_STUDIO)
                        if refundable and appointment.deposit_paid_at and rng.random() < 0.7:
                            appointment.deposit_refunded_at = appointment.cancelled_at + timedelta(days=2)
                else:
                    paid = needs_deposit and rng.random() < 0.65
                    if paid:
                        appointment.status = AppointmentStatus.CONFIRMED
                        appointment.deposit_paid_at = min(booked + timedelta(days=1), now)
                    elif offset < 10 and needs_deposit and rng.random() < 0.5:
                        appointment.created_at = now - timedelta(days=rng.randint(3, 6))  # deposit overdue
                    if offset <= 1:
                        appointment.reminder_sent_at = now - timedelta(hours=2)
                        if rng.random() < 0.7:
                            appointment.attendance_confirmed_at = now - timedelta(hours=1)
                    if offset > 3 and rng.random() < 0.08:
                        # A few future cancellations, some with a refund still to make.
                        appointment.status = AppointmentStatus.CANCELLED
                        appointment.cancellation_reason = CancellationReason.CLIENT_EARLY
                        appointment.cancelled_at = now - timedelta(days=rng.randint(1, 5))
                        appointment.cancelled_by = client.id

                session.add(appointment)
                session.flush()
                if appointment.status != AppointmentStatus.CANCELLED and appointment.id is not None:
                    session.add(BookedSlot(slot_at=scheduled_at, appointment_id=appointment.id))
                    taken.add(scheduled_at)
                counts[appointment.status.value] = counts.get(appointment.status.value, 0) + 1

        # The expenses of the last 3 months and of this month, up to today.
        expenses = 0
        for month_offset in range(-3, 1):
            month_index = today.year * 12 + today.month - 1 + month_offset
            for day_number, description, category, amount in DEMO_EXPENSES:
                day = date(month_index // 12, month_index % 12 + 1, day_number)
                if day <= today:
                    session.add(Expense(day=day, description=description, category=category, amount=amount))
                    expenses += 1

        # Clients can only book published months: open this one and the next.
        for month_offset in (0, 1):
            month_index = today.year * 12 + today.month - 1 + month_offset
            key = (month_index // 12, month_index % 12 + 1)
            if session.get(PublishedMonth, key) is None:
                session.add(PublishedMonth(year=key[0], month=key[1]))

        session.commit()

    print(
        f"Created {len(DEMO_CLIENTS)} clients ({sum(c[4] for c in DEMO_CLIENTS)} registered) "
        f"and {sum(counts.values())} appointments: {counts}"
    )
    print(f"Created {expenses} expenses.")
    print(f"Demo clients log in with their phone and the password {DEMO_PASSWORD!r}.")


if __name__ == "__main__":
    main()
