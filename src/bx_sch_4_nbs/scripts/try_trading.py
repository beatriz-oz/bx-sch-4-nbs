# ruff: noqa: DTZ001
from datetime import datetime, timedelta
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlmodel import Session, select

import bx_sch_4_nbs.routers.admin as admin_router
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.types import AppointmentStatus, Service, TradeItem, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_phone
from bx_sch_4_nbs.main import app

sent: list[tuple] = []
setattr(admin_router, "send_booked_by_studio_notification", lambda *a: sent.append(a))  # noqa: B010
setattr(admin_router, "send_changed_by_studio_notification", lambda *a: sent.append(a))  # noqa: B010

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


email = "tania@trade.test"
tania = User(
    name="Tania",
    last_name="Trade",
    instagram="tania.trade",
    email_encrypted=encrypt_email(email),
    email_hash=hash_email(email),
    phone_encrypted=encrypt_phone("+351917111111"),
    phone_hash=hash_phone("+351917111111"),
    is_active=True,
    email_verified=True,
    approved_at=datetime(2026, 1, 1),
)
session.add(tania)
session.commit()
admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
policy = session.exec(select(Policy)).first()
assert tania.id is not None and admin is not None and policy is not None and policy.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
TANIA = {"Authorization": f"Bearer {create_access_token(tania)}"}
now = utc_now()
far = (now + timedelta(days=310)).replace(hour=10, minute=0, second=0)
TRADE = {
    "service": "Trading",
    "trade_item": "Nails",
    "duration_minutes": 120,
    "estimated_price": "0",
    "notes": "Photos of the studio for Instagram",
    "user_id": tania.id,
}


def book(days: int = 0, **fields: object):
    data = {"scheduled_at": (far + timedelta(days=days)).isoformat() + "Z", **TRADE, **fields}
    return client.post("/v1/admin/appointments", headers=ADMIN, json=data)


# --- Booking a trade ---
r = book(nail_size="L", nail_art_level="Level 2")
check("trade of nails, with size and art for the history -> 201", r.status_code == 201, r.text)
trade = r.json()["detail"] if r.status_code == 201 else {}
check("no price", trade.get("estimated_price") in ("0", "0.00"), trade.get("estimated_price"))
check("the duration she set (2h)", trade.get("duration_minutes") == 120, trade.get("duration_minutes"))
check("what was traded is kept", trade.get("trade_item") == "Nails", trade.get("trade_item"))
check("no deposit", trade.get("deposit_required") is False, trade.get("deposit_required"))
check("the booking email says no deposit", bool(sent) and sent[-1][-1] is False)

r = book(days=1, trade_item="Press-ons", duration_minutes=90)
check("trade of press-ons -> 201", r.status_code == 201, r.text)

for label, fields in [
    ("without what is traded -> 422", {"trade_item": None}),
    ("without the duration -> 422", {"duration_minutes": None}),
    ("without notes -> 422", {"notes": None}),
    ("with a price -> 422", {"estimated_price": "10"}),
    ("press-ons with a size -> 422", {"trade_item": "Press-ons", "nail_size": "M"}),
    ("duration under 15 minutes -> 422", {"duration_minutes": 10}),
]:
    r = book(days=2, **fields)
    check(label, r.status_code == 422, r.status_code)

r = client.post(
    "/v1/admin/appointments",
    headers=ADMIN,
    json={
        "scheduled_at": (far + timedelta(days=3)).isoformat() + "Z",
        "service": "Application",
        "nail_size": "M",
        "nail_art_level": "Level 1",
        "estimated_price": "40",
        "duration_minutes": 60,
        "user_id": tania.id,
    },
)
check("another service with a duration -> 422", r.status_code == 422, r.status_code)

# --- Changing a trade ---
change = {"scheduled_at": far.isoformat() + "Z", **{k: v for k, v in TRADE.items() if k != "user_id"}}
r = client.put(f"/v1/admin/appointments/{trade.get('id')}", headers=ADMIN, json={**change, "duration_minutes": 90})
check(
    "change the planned duration -> 90", r.status_code == 200 and r.json()["detail"]["duration_minutes"] == 90, r.text
)
r = client.put(
    f"/v1/admin/appointments/{trade.get('id')}",
    headers=ADMIN,
    json={
        "scheduled_at": far.isoformat() + "Z",
        "service": "Application",
        "nail_size": "M",
        "nail_art_level": "Level 1",
        "estimated_price": "40",
    },
)
moved = r.json()["detail"] if r.status_code == 200 else {}
check(
    "turned into an application: no trade item, usual 3h",
    moved.get("trade_item") is None and moved.get("duration_minutes") == 180,
    moved,
)

# --- Clients cannot book or simulate trades ---
r = client.get("/v1/prices/simulate", params={"service": "Trading"})
check("public simulator: trading -> 422", r.status_code == 422, r.status_code)

# --- Completing ---
past = Appointment(
    user_id=tania.id,
    scheduled_at=(now - timedelta(days=3)).replace(hour=14, minute=0, second=0),
    status=AppointmentStatus.CONFIRMED,
    service=Service.TRADING,
    trade_item=TradeItem.PRESS_ONS,
    duration_minutes=150,
    estimated_price=0,
    policy_id=policy.id,
    notes="Trade",
)
session.add(past)
session.commit()
assert past.id is not None
r = client.post(f"/v1/admin/appointments/{past.id}/complete", headers=ADMIN, json={"final_price": "5.00"})
check("complete a trade with a price -> 409", r.status_code == 409, r.text)
r = client.post(f"/v1/admin/appointments/{past.id}/complete", headers=ADMIN, json={"final_price": "0"})
check(
    "complete with 0, no duration -> keeps the planned 150",
    r.status_code == 200 and r.json()["detail"]["duration_minutes"] == 150,
    r.text,
)

# --- Reports: apart ---
month = to_studio_time(past.scheduled_at)
r = client.get("/v1/admin/reports", headers=ADMIN, params={"year": month.year})
row = r.json()["detail"]["months"][month.month - 1]
check("reports: the trade counted", row["trades"] >= 1 and row["trade_minutes"] >= 150, row)
check(
    "reports: not in the services table", all(s["service"] != "Trading" for s in row["by_service"]), row["by_service"]
)
items = {t["trade_item"]: t for t in row["trades_by_item"]}
check("reports: by item (press-ons)", items.get("Press-ons", {}).get("completed", 0) >= 1, row["trades_by_item"])
# The trade's 150 minutes stay out of "worked_minutes": recompute from the services table.
check(
    "reports: hours worked exclude trades",
    row["worked_minutes"] == sum(s["worked_minutes"] for s in row["by_service"]),
    row,
)

# --- Export ---
day = month.date()
r = client.get("/v1/admin/appointments/export", headers=ADMIN, params={"start_date": str(day), "end_date": str(day)})
sheet = load_workbook(BytesIO(r.content)).active
assert sheet is not None
labels = {row[4] for row in sheet.iter_rows(min_row=2, values_only=True) if row[4]}
check("export: 'Troca (press-ons)'", "Troca (press-ons)" in labels, labels)

session.close()
transaction.rollback()
connection.close()
