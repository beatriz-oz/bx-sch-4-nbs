# ruff: noqa: DTZ001
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlmodel import Session, select

import bx_sch_4_nbs.routers.admin as admin_router
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.queries.schedule import is_deposit_overdue
from bx_sch_4_nbs.database.types import AppointmentStatus, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_phone
from bx_sch_4_nbs.main import app

# The emails are captured, never sent: (deposit_required) is the last argument of the booking email.
sent: list[tuple] = []
setattr(admin_router, "send_booked_by_studio_notification", lambda *a: sent.append(a))  # noqa: B010

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


email = "paula@presson.test"
paula = User(
    name="Paula",
    last_name="Presson",
    instagram="paula.presson",
    email_encrypted=encrypt_email(email),
    email_hash=hash_email(email),
    phone_encrypted=encrypt_phone("+351916111111"),
    phone_hash=hash_phone("+351916111111"),
    is_active=True,
    email_verified=True,
    approved_at=datetime(2026, 1, 1),
)
session.add(paula)
session.commit()
admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
policy = session.exec(select(Policy)).first()
assert paula.id is not None and admin is not None and policy is not None and policy.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
PAULA = {"Authorization": f"Bearer {create_access_token(paula)}"}
now = utc_now()
far = (now + timedelta(days=300)).replace(hour=10, minute=0, second=0)


def book(**fields: object):
    data = {
        "scheduled_at": far.isoformat() + "Z",
        "service": "Press-on",
        "estimated_price": "38.00",
        "user_id": paula.id,
    }
    return client.post("/v1/admin/appointments", headers=ADMIN, json={**data, **fields})


# --- The studio books press-ons ---
r = book()
check("studio books a press-on without notes -> 201", r.status_code == 201, r.text)
booked = r.json()["detail"] if r.status_code == 201 else {}
check("its price is the one she set", Decimal(booked.get("estimated_price", "0")) == Decimal(38), booked)
check("3 hours long", booked.get("duration_minutes") == 180, booked.get("duration_minutes"))
check("no deposit needed", booked.get("deposit_required") is False, booked.get("deposit_required"))
check("the booking email says no deposit", bool(sent) and sent[-1][-1] is False, sent[-1:] if sent else sent)

r = book(scheduled_at=(far + timedelta(days=1)).isoformat() + "Z", nail_size="M", nail_art_level="Level 1")
check("press-on with size and nail art -> 422", r.status_code == 422, r.status_code)
r = book(scheduled_at=(far + timedelta(days=2)).isoformat() + "Z", notes="Almond, nude with chrome")
check("press-on with notes -> 201", r.status_code == 201, r.text)
r = book(
    scheduled_at=(far + timedelta(days=3)).isoformat() + "Z",
    service="Application",
    nail_size="M",
    nail_art_level="Level 1",
)
check("an application still needs the deposit", r.status_code == 201 and r.json()["detail"]["deposit_required"], r.text)

# --- Payments: press-ons never wait for a deposit ---
r = client.get("/v1/admin/payments", headers=ADMIN)
pending_ids = {a["id"] for a in r.json()["detail"]["pending_deposits"]}
check("not in the pending deposits", booked.get("id") not in pending_ids)
old = Appointment(
    user_id=paula.id,
    scheduled_at=far + timedelta(days=4),
    status=AppointmentStatus.SCHEDULED,
    service=Service.PRESS_ON,
    estimated_price=Decimal(30),
    policy_id=policy.id,
    created_at=now - timedelta(days=30),
)
check("never 'deposit overdue'", not is_deposit_overdue(old, now))

# --- Clients cannot book or simulate press-ons ---
r = client.get("/v1/prices/simulate", params={"service": "Press-on"})
check("public simulator: press-on -> 422", r.status_code == 422, r.status_code)
r = client.post(
    "/v1/appointments/estimate",
    headers=PAULA,
    json={"scheduled_at": far.isoformat() + "Z", "service": "Press-on"},
)
check("client estimate: press-on -> 422", r.status_code == 422, r.status_code)
r = client.get("/v1/appointments", headers=PAULA)
mine = next((a for a in r.json()["detail"] if a["id"] == booked.get("id")), {})
check("her list: no deposit needed", mine.get("deposit_required") is False, mine)
check("her list: she cannot change it herself", mine.get("can_change") is False, mine)

# --- Completing: the final price is the one she set ---
past = Appointment(
    user_id=paula.id,
    scheduled_at=(now - timedelta(days=2)).replace(hour=14, minute=0, second=0),
    status=AppointmentStatus.CONFIRMED,
    service=Service.PRESS_ON,
    estimated_price=Decimal(40),
    policy_id=policy.id,
)
session.add(past)
session.commit()
assert past.id is not None
r = client.post(f"/v1/admin/appointments/{past.id}/estimate", headers=ADMIN, json={})
check(
    "final price estimate = the price she set",
    r.status_code == 200 and Decimal(r.json()["detail"]["price"]) == 40,
    r.text,
)
r = client.post(
    f"/v1/admin/appointments/{past.id}/complete",
    headers=ADMIN,
    json={"final_price": "42.00", "duration_minutes": 170},
)
check("complete a press-on -> 200", r.status_code == 200, r.text)

# --- Reports and export ---
month = to_studio_time(past.scheduled_at)
r = client.get("/v1/admin/reports", headers=ADMIN, params={"year": month.year})
row = r.json()["detail"]["months"][month.month - 1]
press = next((s for s in row["by_service"] if s["service"] == "Press-on"), None)
check("reports: press-on as its own service", press is not None and Decimal(press["revenue"]) >= 42, row["by_service"])

day = month.date()
r = client.get(
    "/v1/admin/appointments/export",
    headers=ADMIN,
    params={"start_date": str(day), "end_date": str(day), "language": "pt"},
)
sheet = load_workbook(BytesIO(r.content)).active
assert sheet is not None
services = {row[4] for row in sheet.iter_rows(min_row=2, values_only=True) if row[4]}
check("export: 'Press-on' in the service column", "Press-on" in services, services)

# --- Expenses: the new category ---
r = client.post(
    "/v1/admin/expenses",
    headers=ADMIN,
    json={"day": str(day), "description": "Press-on tips", "category": "Press-ons", "amount": "19.90"},
)
check("expense in the Press-ons category -> 201", r.status_code == 201, r.text)
r = client.get("/v1/admin/reports", headers=ADMIN, params={"year": month.year})
cats = {
    c["category"]: Decimal(c["amount"]) for c in r.json()["detail"]["months"][month.month - 1]["expenses_by_category"]
}
check("reports: Press-ons expenses", cats.get("Press-ons", Decimal(0)) >= Decimal("19.90"), cats)

session.close()
transaction.rollback()
connection.close()
