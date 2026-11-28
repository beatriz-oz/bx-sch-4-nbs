# ruff: noqa: DTZ001
"""
The studio fixes an appointment already completed (e.g. booked as maintenance, but it was an application).

    uv run --with httpx python -m bx_sch_4_nbs.scripts.try_completed_edits
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, BookedSlot, Policy, User
from bx_sch_4_nbs.database.types import AppointmentStatus, NailArtLevel, NailSize, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_phone
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


email = "ana@completed-edits.test"
ana = User(
    name="Anafix",
    last_name="Test",
    instagram="ana.completededits",
    email_encrypted=encrypt_email(email),
    email_hash=hash_email(email),
    phone_encrypted=encrypt_phone("+351916111111"),
    phone_hash=hash_phone("+351916111111"),
    is_active=True,
    email_verified=True,
    approved_at=datetime(2026, 1, 1),
)
session.add(ana)
session.flush()
admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
policy = session.exec(select(Policy)).first()
assert admin is not None and policy is not None and policy.id is not None and ana.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
CLIENT = {"Authorization": f"Bearer {create_access_token(ana)}"}
ANA, POLICY = ana.id, policy.id
now = utc_now()
# Odd minutes, far in the past: no other appointment of the local database is there.
past = (now - timedelta(days=400)).replace(hour=9, minute=13, second=0, microsecond=0)


def make(scheduled_at: datetime, status: AppointmentStatus = AppointmentStatus.COMPLETED) -> int:
    appointment = Appointment(
        user_id=ANA,
        scheduled_at=scheduled_at,
        policy_id=POLICY,
        status=status,
        service=Service.MAINTENANCE,
        nail_size=NailSize.MEDIUM,
        nail_art_level=NailArtLevel.LEVEL_1,
        estimated_price=Decimal(30),
        final_price=Decimal(30) if status == AppointmentStatus.COMPLETED else None,
        duration_minutes=150 if status == AppointmentStatus.COMPLETED else None,
    )
    session.add(appointment)
    session.flush()
    assert appointment.id is not None
    session.add(BookedSlot(slot_at=scheduled_at, appointment_id=appointment.id))
    session.commit()
    return appointment.id


def body(scheduled_at: datetime, **extra: Any) -> dict[str, Any]:
    return {
        "scheduled_at": to_studio_time(scheduled_at).replace(tzinfo=None).isoformat(),
        "service": "Application",
        "nail_size": "L",
        "nail_art_level": "Level 2",
        "final_price": "45.00",
        "duration_minutes": 197,
        "completion_notes": "It was an application after all",
        **extra,
    }


done = make(past)
r = client.put(f"/v1/admin/appointments/{done}/completed", json=body(past), headers=ADMIN)
detail = r.json().get("detail", {})
check("fix a completed maintenance into an application -> 200", r.status_code == 200, r.text)
check(
    "service, size, art, price and duration are saved",
    detail.get("service") == "Application"
    and detail.get("nail_size") == "L"
    and detail.get("nail_art_level") == "Level 2"
    and detail.get("final_price") == "45.00"
    and detail.get("duration_minutes") == 197,
    detail,
)
check(
    "it stays completed, the estimate as booked",
    detail.get("status") == "Completed" and detail.get("estimated_price") == "30.00",
    detail,
)
check("the notes from the appointment are saved", detail.get("completion_notes") == "It was an application after all")

later = past + timedelta(days=1)
r = client.put(f"/v1/admin/appointments/{done}/completed", json=body(later), headers=ADMIN)
check("move it to another day -> 200", r.status_code == 200, r.text)
session.expire_all()
check(
    "its booked slot moves with it",
    session.get(BookedSlot, later) is not None and session.get(BookedSlot, past) is None,
)

other = make(past)
r = client.put(f"/v1/admin/appointments/{other}/completed", json=body(later), headers=ADMIN)
check("onto the time of another appointment -> 409", r.status_code == 409, r.text)

r = client.put(f"/v1/admin/appointments/{done}/completed", json=body(later, service="Removal"), headers=ADMIN)
check("removal with a nail size -> 422", r.status_code == 422, r.text)
r = client.put(
    f"/v1/admin/appointments/{done}/completed",
    json=body(later, service="Removal", nail_size=None, nail_art_level=None),
    headers=ADMIN,
)
check("removal without size -> 200", r.status_code == 200, r.text)
r = client.put(f"/v1/admin/appointments/{done}/completed", json=body(later, duration_minutes=10), headers=ADMIN)
check("under 15 minutes -> 422", r.status_code == 422)
r = client.put(
    f"/v1/admin/appointments/{done}/completed",
    json=body(later, service="Trading", trade_item="Nails", notes="trade"),
    headers=ADMIN,
)
check("a trade with a price -> 422", r.status_code == 422)

active = make(now + timedelta(days=300, minutes=7), AppointmentStatus.SCHEDULED)
r = client.put(f"/v1/admin/appointments/{active}/completed", json=body(past + timedelta(days=3)), headers=ADMIN)
check("an appointment not completed yet -> 409 (it has its own change)", r.status_code == 409, r.text)
r = client.put("/v1/admin/appointments/99999999/completed", json=body(past), headers=ADMIN)
check("unknown appointment -> 404", r.status_code == 404)
r = client.put(f"/v1/admin/appointments/{done}/completed", json=body(later), headers=CLIENT)
check("a client cannot -> 403", r.status_code == 403, r.status_code)

session.close()
transaction.rollback()
connection.close()
