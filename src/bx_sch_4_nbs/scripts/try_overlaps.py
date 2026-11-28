# ruff: noqa: DTZ001
"""
Times that overlap an appointment: closed for the clients, a warning for the studio.

    uv run --with httpx python -m bx_sch_4_nbs.scripts.try_overlaps
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import bx_sch_4_nbs.routers.admin as admin_router
from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, BookedSlot, Policy, PublishedMonth, User
from bx_sch_4_nbs.database.queries import availability
from bx_sch_4_nbs.database.types import AppointmentStatus, NailArtLevel, NailSize, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_studio_time, to_utc, utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_phone
from bx_sch_4_nbs.main import app

# The emails are captured, never sent.
setattr(admin_router, "send_booked_by_studio_notification", lambda *a: None)  # noqa: B010
setattr(admin_router, "send_changed_by_studio_notification", lambda *a: None)  # noqa: B010

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
    email = f"{name.lower()}@overlaps.test"
    user = User(
        name=name,
        last_name="Test",
        instagram=f"{name.lower()}.overlaps",
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
ana = make_user("Anaoverlap", "+351915111111")
assert admin is not None and policy is not None and policy.id is not None and ana.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
POLICY, ANA = policy.id, ana.id
now = utc_now()

# A month about two months ahead, published inside this transaction, with days fully free.
today = to_studio_time(now).date()
month_start = (today.replace(day=1) + timedelta(days=62)).replace(day=1)
if session.get(PublishedMonth, (month_start.year, month_start.month)) is None:
    session.add(PublishedMonth(year=month_start.year, month=month_start.month))
    session.flush()
free_days: dict[date, list[datetime]] = {}
for slot in availability.available_slots(session, month_start.year, month_start.month):
    free_days.setdefault(to_studio_time(slot).date(), []).append(slot)
default_times = [time(10), time(14), time(17)]
assert settings.appointment_slots == default_times, "These checks expect the 10:00, 14:00 and 17:00 slots."
full_days = [day for day, slots in free_days.items() if len(slots) == len(default_times)]
assert len(full_days) >= 6, "Not enough free days in the test month."


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return to_utc(datetime.combine(day, time(hour, minute)))


def make(scheduled_at: datetime, service: Service = Service.APPLICATION, **fields: Any) -> int:
    sized = service in (Service.APPLICATION, Service.MAINTENANCE)
    appointment = Appointment(
        user_id=ANA,
        scheduled_at=scheduled_at,
        policy_id=POLICY,
        status=fields.pop("status", AppointmentStatus.SCHEDULED),
        service=service,
        nail_size=NailSize.MEDIUM if sized else None,
        nail_art_level=NailArtLevel.LEVEL_1 if sized else None,
        estimated_price=Decimal(40),
        **fields,
    )
    session.add(appointment)
    session.flush()
    assert appointment.id is not None
    if appointment.status in availability.ACTIVE_STATUSES:
        session.add(BookedSlot(slot_at=scheduled_at, appointment_id=appointment.id))
    session.commit()
    return appointment.id


def open_hours(day: date) -> list[int]:
    return [
        to_studio_time(slot).hour
        for slot in availability.available_slots(session, day.year, day.month)
        if to_studio_time(slot).date() == day
    ]


# ================= Closed for the clients =================
d11, d13, d15, d_removal, d_cancelled, d_trade = full_days[:6]

make(at(d11, 11))
check("booked at 11:00 -> 10:00 closes, 14:00 and 17:00 stay open", open_hours(d11) == [14, 17], open_hours(d11))

make(at(d13, 13))
check("booked at 13:00 -> 14:00 closes, 10:00 and 17:00 stay open", open_hours(d13) == [10, 17], open_hours(d13))

make(at(d15, 15))
check("booked at 15:00 -> 14:00 and 17:00 close, 10:00 stays open", open_hours(d15) == [10], open_hours(d15))

make(at(d_removal, 12, 30), Service.REMOVAL)
check(
    "a 1h removal at 12:30 (ends 13:30) -> 10:00 closes (it runs to 13:00), 14:00 stays open",
    open_hours(d_removal) == [14, 17],
    open_hours(d_removal),
)

make(at(d_cancelled, 11), status=AppointmentStatus.CANCELLED)
check("a cancelled appointment closes nothing", open_hours(d_cancelled) == [10, 14, 17], open_hours(d_cancelled))

make(at(d_trade, 7), Service.TRADING, duration_minutes=240, notes="trade")
check("a trade uses its own duration: 07:00 for 4h closes 10:00", open_hours(d_trade) == [14, 17], open_hours(d_trade))

check(
    "a client cannot book it either (is_slot_available)",
    not availability.is_slot_available(session, at(d15, 17), None),
)

# --- the opening hours agenda shows them ---
agenda = availability.month_agenda(session, d15.year, d15.month)
slots = {slot.time.hour: slot for slot in agenda[d15].slots}
check("agenda: 14:00 and 17:00 are marked as overlapped", slots[14].is_overlapped and slots[17].is_overlapped)
check("agenda: ...but not booked, and still open by the studio", not slots[14].is_booked and slots[14].is_open)
check("agenda: 10:00 is free", not slots[10].is_overlapped and not slots[10].is_booked)
response = client.get("/v1/admin/agenda", params={"year": d15.year, "month": d15.month}, headers=ADMIN)
day_json = next(day for day in response.json()["detail"]["days"] if day["day"] == d15.isoformat())
check("the API sends is_overlapped", [s["is_overlapped"] for s in day_json["slots"]] == [False, True, True], day_json)

# ================= A warning for the studio =================
d_admin = full_days[6] if len(full_days) > 6 else None
if d_admin is None:
    check("enough free days for the studio checks", False, len(full_days))
else:
    at14 = make(at(d_admin, 14))

    day_admin: date = d_admin

    def body(hour: int, minute: int = 0, **extra: Any) -> dict[str, Any]:
        return {
            "scheduled_at": datetime.combine(day_admin, time(hour, minute)).isoformat(),
            "service": "Application",
            "nail_size": "M",
            "nail_art_level": "Level 1",
            "estimated_price": "40.00",
            "user_id": ANA,
            **extra,
        }

    count_before = len(session.exec(select(Appointment).where(Appointment.user_id == ANA)).all())
    r = client.post("/v1/admin/appointments", json=body(13), headers=ADMIN)
    detail = r.json().get("detail")
    check(
        "13:00 while 14:00 is booked -> 409 overlap", r.status_code == 409 and detail.get("code") == "overlap", r.text
    )
    check(
        "...listing the 14:00 appointment, its end and the client",
        detail.get("appointments")
        == [{"id": at14, "time": "14:00", "end": "17:00", "client": "Anaoverlap", "service": "Application"}],
        detail,
    )
    session.expire_all()
    count_after = len(session.exec(select(Appointment).where(Appointment.user_id == ANA)).all())
    check("...and nothing was booked", count_after == count_before)

    r = client.post("/v1/admin/appointments", json=body(13, confirm_overlap=True), headers=ADMIN)
    check("confirmed -> 201", r.status_code == 201, r.text)
    at13 = r.json()["detail"]["id"] if r.status_code == 201 else None

    r = client.post("/v1/admin/appointments", json=body(14), headers=ADMIN)
    check(
        "the exact same time is still 'already booked', not an overlap",
        r.status_code == 409 and isinstance(r.json()["detail"], str),
        r.text,
    )

    r = client.post("/v1/admin/appointments", json=body(17), headers=ADMIN)
    check("17:00 right after the 14:00 (ends 17:00) -> no warning, 201", r.status_code == 201, r.text)

    r = client.post(
        "/v1/admin/appointments",
        json={**body(9), "service": "Removal", "nail_size": None, "nail_art_level": None},
        headers=ADMIN,
    )
    check("a 1h removal at 09:00 (13:00 starts later) -> 201", r.status_code == 201, r.text)

    # --- changes ---
    if at13 is not None:
        r = client.put(f"/v1/admin/appointments/{at13}", json=body(13, notes="only the notes"), headers=ADMIN)
        check("changing only the notes of an overlapping appointment -> no new warning", r.status_code == 200, r.text)

    r = client.put(f"/v1/admin/appointments/{at14}", json=body(15), headers=ADMIN)
    check(
        "moving 14:00 to 15:00 (over the 17:00) -> 409 overlap",
        r.status_code == 409 and r.json()["detail"].get("code") == "overlap",
        r.text,
    )
    listed = [a["time"] for a in r.json()["detail"].get("appointments", [])] if r.status_code == 409 else []
    check("...it lists the others, not itself", listed == ["13:00", "17:00"], listed)
    r = client.put(f"/v1/admin/appointments/{at14}", json=body(15, confirm_overlap=True), headers=ADMIN)
    check("confirmed -> 200", r.status_code == 200, r.text)

session.close()
transaction.rollback()
connection.close()
