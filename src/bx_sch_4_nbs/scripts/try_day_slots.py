from datetime import date, datetime, time, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, BookedSlot, Policy, User
from bx_sch_4_nbs.database.queries import availability, day_slots
from bx_sch_4_nbs.database.types import AppointmentStatus, NailSize, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_studio_time, to_utc, utc_now
from bx_sch_4_nbs.main import app

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


admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
policy = session.exec(select(Policy)).first()
assert admin is not None and policy is not None and policy.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}

# Two open days, about two months from now: one with its own slots, one with the default.
today = to_studio_time(utc_now()).date()
start = (today.replace(day=1) + timedelta(days=62)).replace(day=1)
open_days = [
    start + timedelta(days=n) for n in range(28) if (start + timedelta(days=n)).weekday() in settings.open_weekdays
]
custom_day, default_day = open_days[0], open_days[1]
CUSTOM = [time(10, 0), time(14, 0), time(16, 0)]
DEFAULT = settings.appointment_slots


def times_of(slots: list[datetime], day: date) -> list[time]:
    return [to_studio_time(s).time() for s in slots if to_studio_time(s).date() == day]


def free(day: date, size: NailSize | None = None) -> list[time]:
    return times_of(availability.available_slots(session, day.year, day.month, size, require_published=False), day)


# --- Route validation ---
r = client.put(
    "/v1/admin/day-slots", headers=ADMIN, json={"day": str(today - timedelta(days=1)), "slot_times": ["10:00"]}
)
check("day in the past -> 422", r.status_code == 422, r.text)
r = client.put("/v1/admin/day-slots", headers=ADMIN, json={"day": str(custom_day), "slot_times": ["10:00", "10:00"]})
check("same time twice -> 422", r.status_code == 422, r.text)
r = client.put("/v1/admin/day-slots", headers=ADMIN, json={"day": str(custom_day), "slot_times": ["10:10"]})
check("time not in steps of 15 -> 422", r.status_code == 422, r.text)
r = client.put("/v1/admin/day-slots", headers=ADMIN, json={"day": str(custom_day), "slot_times": ["23:00"]})
check("time outside 07-21 -> 422", r.status_code == 422, r.text)
r = client.put("/v1/admin/day-slots", json={"day": str(custom_day), "slot_times": ["10:00"]})
check("without login -> 401", r.status_code == 401, r.status_code)

# --- Setting a day ---
r = client.put(
    "/v1/admin/day-slots", headers=ADMIN, json={"day": str(custom_day), "slot_times": ["16:00", "10:00", "14:00"]}
)
body = r.json()
check(
    "set slots -> 200, sorted", r.status_code == 200 and body["detail"] == ["10:00:00", "14:00:00", "16:00:00"], r.text
)
check("no bookings -> no warning", body.get("warning") is None, body)

check("custom day: availability uses its own slots", free(custom_day) == CUSTOM, free(custom_day))
check("default day: unchanged", free(default_day) == DEFAULT, free(default_day))
check(
    "XL on custom day: first and last",
    free(custom_day, NailSize.XLARGE) == [time(10, 0), time(16, 0)],
    free(custom_day, NailSize.XLARGE),
)
check(
    "XXL on default day: first and last",
    free(default_day, NailSize.XXLARGE) == [DEFAULT[0], DEFAULT[-1]],
    free(default_day, NailSize.XXLARGE),
)
check("M on custom day: every slot", free(custom_day, NailSize.MEDIUM) == CUSTOM)

# --- Schedule exceptions follow the day's slots ---
r = client.put(
    "/v1/admin/schedule-exceptions",
    headers=ADMIN,
    json={"day": str(custom_day), "slot_time": "17:00", "is_open": False},
)
check("exception at a removed time -> 422", r.status_code == 422, r.text)
r = client.put(
    "/v1/admin/schedule-exceptions",
    headers=ADMIN,
    json={"day": str(custom_day), "slot_time": "16:00", "is_open": False},
)
check("exception at the new time -> 200", r.status_code == 200, r.text)
check("closed 16:00 is gone from availability", free(custom_day) == CUSTOM[:2], free(custom_day))
r = client.put(
    "/v1/admin/schedule-exceptions",
    headers=ADMIN,
    json={"day": str(default_day), "slot_time": "17:00", "is_open": False},
)
check("exception at a default time on a default day -> 200", r.status_code == 200, r.text)

# --- Agenda ---
r = client.get("/v1/admin/agenda", headers=ADMIN, params={"year": custom_day.year, "month": custom_day.month})
days = {d["day"]: d for d in r.json()["detail"]["days"]} if r.status_code == 200 else {}
c, d = days.get(str(custom_day), {}), days.get(str(default_day), {})
check("agenda: custom day flagged", c.get("custom_times") is True, c)
check(
    "agenda: custom day has its 3 slots",
    [s["time"] for s in c.get("slots", [])] == ["10:00:00", "14:00:00", "16:00:00"],
    c,
)
check("agenda: default day not flagged", d.get("custom_times") is False, d)

# --- Removing a time that is booked: kept, with a warning ---
client_user = session.exec(select(User).where(User.role == UserRole.USER)).first()
assert client_user is not None and client_user.id is not None
slot_at = to_utc(datetime.combine(custom_day, time(14, 0)))
appointment = Appointment(
    user_id=client_user.id,
    scheduled_at=slot_at,
    status=AppointmentStatus.SCHEDULED,
    service=Service.APPLICATION,
    nail_size=NailSize.MEDIUM,
    estimated_price=30,
    policy_id=policy.id,
    policies_accepted_at=utc_now(),
)
session.add(appointment)
session.flush()
assert appointment.id is not None
session.add(BookedSlot(slot_at=slot_at, appointment_id=appointment.id))
session.flush()

r = client.put("/v1/admin/day-slots", headers=ADMIN, json={"day": str(custom_day), "slot_times": ["10:00", "15:00"]})
body = r.json()
check("removing a booked time -> 200 with a warning", r.status_code == 200 and body.get("warning"), body)
kept = session.get(Appointment, appointment.id)
check("the appointment is kept", kept is not None and kept.status == AppointmentStatus.SCHEDULED)

# --- Back to default ---
r = client.put("/v1/admin/day-slots", headers=ADMIN, json={"day": str(custom_day), "slot_times": []})
check(
    "empty list -> default slots",
    r.status_code == 200 and r.json()["detail"] == [t.isoformat() for t in DEFAULT],
    r.text,
)
check("query: back to default", day_slots.slots_for_day(session, custom_day) == DEFAULT)

session.close()
transaction.rollback()
connection.close()
