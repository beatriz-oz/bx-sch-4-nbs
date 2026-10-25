# ruff: noqa: DTZ001
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import bx_sch_4_nbs.routers.admin as admin_router
import bx_sch_4_nbs.routers.appointments as appointments_router
from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, BookedSlot, Policy, PublishedMonth, User
from bx_sch_4_nbs.database.queries import availability
from bx_sch_4_nbs.database.queries.prices import calculate_price
from bx_sch_4_nbs.database.types import AppointmentStatus, NailArtLevel, NailSize, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_studio_time, to_utc, utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_phone
from bx_sch_4_nbs.main import app

# The emails are captured, never sent.
sent: list[tuple[str, tuple]] = []
setattr(appointments_router, "send_changed_by_client_notification", lambda *a: sent.append(("studio", a)))  # noqa: B010
setattr(admin_router, "send_changed_by_studio_notification", lambda *a: sent.append(("client", a)))  # noqa: B010

connection = engine.connect()
transaction = connection.begin()
session = Session(bind=connection, join_transaction_mode="create_savepoint")


def override_session():
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise


app.dependency_overrides[get_session] = override_session
client = TestClient(app, raise_server_exceptions=False)


def check(label: str, ok: bool, detail: object = "") -> None:
    print("OK    " if ok else "ERRO  ", label, detail if not ok else "")


def make_user(name: str, phone: str) -> User:
    email = f"{name.lower()}@changes.test"
    user = User(
        name=name,
        last_name="Test",
        instagram=f"{name.lower()}.changes",
        email_encrypted=encrypt_email(email),
        email_hash=hash_email(email),
        phone_encrypted=encrypt_phone(phone),
        phone_hash=hash_phone(phone),
        is_active=True,
        email_verified=True,
        approved_at=datetime(2026, 1, 1),
    )
    session.add(user)
    session.flush()
    return user


admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
policy = session.exec(select(Policy)).first()
ana = make_user("Anachange", "+351914111111")
bia = make_user("Biachange", "+351914222222")
assert admin is not None and policy is not None and policy.id is not None and ana.id is not None and bia.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
ANA = {"Authorization": f"Bearer {create_access_token(ana)}"}
BIA = {"Authorization": f"Bearer {create_access_token(bia)}"}
POLICY = policy.id
now = utc_now()

# A month about two months ahead, published inside this transaction, with free days.
today = to_studio_time(now).date()
month_start = (today.replace(day=1) + timedelta(days=62)).replace(day=1)
if session.get(PublishedMonth, (month_start.year, month_start.month)) is None:
    session.add(PublishedMonth(year=month_start.year, month=month_start.month))
    session.flush()
free = availability.available_slots(session, month_start.year, month_start.month)
free_days: dict[date, list[datetime]] = {}
for slot in free:
    free_days.setdefault(to_studio_time(slot).date(), []).append(slot)
# Days with all three default slots free.
full_days = [day for day, slots in free_days.items() if len(slots) == len(settings.appointment_slots)]
assert len(full_days) >= 3, "Not enough free days in the test month."
day1, day2, day3 = full_days[:3]
first, middle, last = free_days[day1]


def make(user_id: int, scheduled_at: datetime, **fields: Any) -> int:
    fields = {
        "status": AppointmentStatus.SCHEDULED,
        "service": Service.APPLICATION,
        "nail_size": NailSize.MEDIUM,
        "nail_art_level": NailArtLevel.LEVEL_1,
        "estimated_price": Decimal(40),
        **fields,
    }
    appointment = Appointment(user_id=user_id, scheduled_at=scheduled_at, policy_id=POLICY, **fields)
    session.add(appointment)
    session.flush()
    assert appointment.id is not None
    if appointment.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED):
        session.add(BookedSlot(slot_at=scheduled_at, appointment_id=appointment.id))
    # Committed (to the outer test transaction): a 409 later rolls back only that request.
    session.commit()
    return appointment.id


def body(scheduled_at: datetime, size: str | None = "M", art: str | None = "Level 1", service: str = "Application"):
    return {
        "scheduled_at": scheduled_at.isoformat() + "Z",
        "service": service,
        "nail_size": size,
        "nail_art_level": art,
        "broken_nails": 0,
        "has_other_professional_nails": False,
    }


def get(appointment_id: int) -> Appointment:
    session.expire_all()
    appointment = session.get(Appointment, appointment_id)
    assert appointment is not None
    return appointment


# ================= The client =================
far = make(ana.id, middle, reminder_sent_at=now, attendance_confirmed_at=now)

r = client.put(f"/v1/appointments/{far}", headers=ANA, json=body(free_days[day2][0]))
check("client moves her appointment -> 200", r.status_code == 200, r.text)
moved = get(far)
check("the new time is saved", moved.scheduled_at == free_days[day2][0], moved.scheduled_at)
check("the old slot is free again", session.get(BookedSlot, middle) is None)
check(
    "the new slot is taken by it",
    (s := session.get(BookedSlot, free_days[day2][0])) is not None and s.appointment_id == far,
)
check("reminder and confirmation start again", moved.reminder_sent_at is None and moved.attendance_confirmed_at is None)
check("the studio got an email", [k for k, _ in sent] == ["studio"], sent)
sent.clear()

r = client.put(f"/v1/appointments/{far}", headers=ANA, json=body(free_days[day2][0], size="L", art="Level 2"))
expected = calculate_price(
    session, service=Service.APPLICATION, nail_size=NailSize.LARGE, nail_art_level=NailArtLevel.LEVEL_2
)
check("same time, other details -> 200", r.status_code == 200, r.text)
check(
    "the price is calculated again", Decimal(r.json()["detail"]["appointment"]["estimated_price"]) == expected, r.text
)
check("details changed, studio told again", len(sent) == 1, sent)
sent.clear()

# XL/XXL only in the first or the last slot of the day.
mid_appointment = make(ana.id, free_days[day3][1])
r = client.put(f"/v1/appointments/{mid_appointment}", headers=ANA, json=body(free_days[day3][1], size="XL"))
check("same middle time, now XL -> 409", r.status_code == 409, r.text)
r = client.put(f"/v1/appointments/{mid_appointment}", headers=ANA, json=body(free_days[day3][0], size="XL"))
check("XL moved to the first slot -> 200", r.status_code == 200, r.text)

# Someone else's appointment, or a time already booked.
bia_appointment = make(bia.id, first)
r = client.put(f"/v1/appointments/{bia_appointment}", headers=ANA, json=body(free_days[day1][2]))
check("someone else's appointment -> 404", r.status_code == 404, r.status_code)
r = client.put(f"/v1/appointments/{far}", headers=ANA, json=body(first))
check("a time already booked -> 409", r.status_code == 409, r.text)
check("nothing changed after the 409", get(far).scheduled_at == free_days[day2][0])

# Too late, not active, or arranged by the studio.
soon = make(ana.id, (now + timedelta(hours=30)).replace(second=0))
r = client.put(f"/v1/appointments/{soon}", headers=ANA, json=body(free_days[day1][2]))
check("less than 48h before -> 409", r.status_code == 409 and "48" in r.json()["detail"], r.text)
cancelled = make(ana.id, free_days[day1][2] + timedelta(days=1), status=AppointmentStatus.CANCELLED)
r = client.put(f"/v1/appointments/{cancelled}", headers=ANA, json=body(free_days[day1][2]))
check("a cancelled appointment -> 409", r.status_code == 409, r.text)
other = make(
    ana.id, free_days[day3][2], service=Service.OTHER, nail_size=None, nail_art_level=None, notes="Nail repair"
)
r = client.put(f"/v1/appointments/{other}", headers=ANA, json=body(free_days[day1][2]))
check("OTHER (arranged by the studio) -> 409", r.status_code == 409, r.text)

r = client.get("/v1/appointments", headers=ANA)
can = {a["id"]: a["can_change"] for a in r.json()["detail"]}
check("can_change: true far ahead", can.get(far) is True, can)
check("can_change: false within 48h", can.get(soon) is False, can)
check("can_change: false when cancelled", can.get(cancelled) is False, can)
check("can_change: false for OTHER", can.get(other) is False, can)

# ================= The studio =================
sent.clear()
r = client.put(f"/v1/admin/appointments/{soon}", headers=ANA, json={})
check("a client on the admin route -> 403", r.status_code == 403, r.status_code)


def studio_body(scheduled_at: datetime, price: str = "45.00", notes: str | None = None, **extra: Any) -> dict:
    return {**body(scheduled_at), "estimated_price": price, "notes": notes, **extra}


# Within 48h and on a Monday at noon: the studio can.
monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
monday_noon = to_utc(datetime.combine(monday, time(12, 0)))
r = client.put(f"/v1/admin/appointments/{soon}", headers=ADMIN, json=studio_body(monday_noon, notes="Moved by phone"))
check("studio moves any appointment, any time -> 200", r.status_code == 200, r.text)
check("price and notes saved", get(soon).estimated_price == Decimal(45) and get(soon).notes == "Moved by phone")
moved_far_ahead = not (monday_noon <= now + timedelta(hours=settings.reminder_hours_before))
check(
    "the client got an email (when not a squeeze-in)",
    (len(sent) == 1 and sent[0][0] == "client") if moved_far_ahead else sent == [],
    sent,
)
sent.clear()

r = client.put(f"/v1/admin/appointments/{soon}", headers=ADMIN, json=studio_body(monday_noon, price="50.00"))
check("only the price changed -> 200, no email", r.status_code == 200 and sent == [], sent)

r = client.put(f"/v1/admin/appointments/{soon}", headers=ADMIN, json=studio_body(first))
check("studio: a time already booked -> 409", r.status_code == 409, r.text)

squeeze = (now + timedelta(hours=3)).replace(second=0)
r = client.put(f"/v1/admin/appointments/{soon}", headers=ADMIN, json=studio_body(squeeze))
check("moved into the next hours -> 200", r.status_code == 200, r.text)
check("squeeze-in: attendance confirmed, no email", get(soon).attendance_confirmed_at is not None and sent == [], sent)

done = make(ana.id, (now - timedelta(days=3)).replace(second=0), status=AppointmentStatus.COMPLETED)
r = client.put(f"/v1/admin/appointments/{done}", headers=ADMIN, json=studio_body(free_days[day1][2]))
check("studio: a completed appointment -> 409", r.status_code == 409, r.text)
r = client.put("/v1/admin/appointments/999999", headers=ADMIN, json=studio_body(free_days[day1][2]))
check("studio: unknown appointment -> 404", r.status_code == 404, r.status_code)
r = client.put(
    f"/v1/admin/appointments/{soon}",
    headers=ADMIN,
    json=studio_body(free_days[day1][2], service="Other", nail_size=None, nail_art_level=None),
)
check("studio: OTHER without a description -> 422", r.status_code == 422, r.status_code)

session.close()
transaction.rollback()
connection.close()
