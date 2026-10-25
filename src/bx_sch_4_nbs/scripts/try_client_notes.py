# ruff: noqa: DTZ001
from datetime import datetime, timedelta
from decimal import Decimal

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


email = "carla@notes.test"
carla = User(
    name="Carla",
    last_name="Notes",
    instagram="carla.notes",
    email_encrypted=encrypt_email(email),
    email_hash=hash_email(email),
    phone_encrypted=encrypt_phone("+351915111111"),
    phone_hash=hash_phone("+351915111111"),
    is_active=True,
    email_verified=True,
    approved_at=datetime(2026, 1, 1),
)
session.add(carla)
session.flush()
admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
policy = session.exec(select(Policy)).first()
assert carla.id is not None and admin is not None and policy is not None and policy.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
CARLA = {"Authorization": f"Bearer {create_access_token(carla)}"}

# One appointment, to see the notes in the calendar too.
when = (utc_now() + timedelta(days=200)).replace(hour=10, minute=0, second=0)
appointment = Appointment(
    user_id=carla.id,
    scheduled_at=when,
    status=AppointmentStatus.SCHEDULED,
    service=Service.APPLICATION,
    nail_size=NailSize.MEDIUM,
    nail_art_level=NailArtLevel.LEVEL_1,
    estimated_price=Decimal(40),
    policy_id=policy.id,
)
session.add(appointment)
session.flush()
assert appointment.id is not None
session.add(BookedSlot(slot_at=when, appointment_id=appointment.id))
session.commit()
URL = f"/v1/admin/clients/{carla.id}/notes"
NOTE = "Pele sensível. Prefere formato amendoado."

# --- Writing ---
r = client.put(URL, headers=ADMIN, json={"notes": f"  {NOTE}  "})
check("save notes -> 200", r.status_code == 200, r.text)
check("trimmed, in the profile", r.json()["detail"]["studio_notes"] == NOTE, r.json()["detail"].get("studio_notes"))
r = client.get(f"/v1/admin/clients/{carla.id}", headers=ADMIN)
check("profile shows the notes", r.json()["detail"]["studio_notes"] == NOTE, r.text[:200])

day = to_studio_time(when).date()
r = client.get("/v1/admin/appointments", headers=ADMIN, params={"start_date": str(day), "end_date": str(day)})
mine = [a for a in r.json()["detail"] if a["id"] == appointment.id]
check(
    "the calendar shows them on her appointment",
    len(mine) == 1 and mine[0]["client"]["studio_notes"] == NOTE,
    mine,
)

# --- Never to the client ---
r = client.get("/v1/auth/me", headers=CARLA)
check(
    "/auth/me has no studio notes", r.status_code == 200 and "studio_notes" not in r.text and NOTE not in r.text, r.text
)
r = client.get("/v1/appointments", headers=CARLA)
check("her appointments have no studio notes", r.status_code == 200 and NOTE not in r.text, r.text[:200])
r = client.put(URL, headers=CARLA, json={"notes": "hack"})
check("a client cannot write them -> 403", r.status_code == 403, r.status_code)

# --- Limits and clearing ---
r = client.put(URL, headers=ADMIN, json={"notes": "x" * 2001})
check("more than 2000 characters -> 422", r.status_code == 422, r.status_code)
r = client.put("/v1/admin/clients/999999/notes", headers=ADMIN, json={"notes": "x"})
check("unknown client -> 404", r.status_code == 404, r.status_code)
r = client.put(URL, headers=ADMIN, json={"notes": "   "})
check("blank clears them", r.status_code == 200 and r.json()["detail"]["studio_notes"] is None, r.text[:200])
r = client.put(URL, headers=ADMIN, json={"notes": None})
check("null clears them too", r.status_code == 200 and r.json()["detail"]["studio_notes"] is None, r.text[:200])

session.close()
transaction.rollback()
connection.close()
