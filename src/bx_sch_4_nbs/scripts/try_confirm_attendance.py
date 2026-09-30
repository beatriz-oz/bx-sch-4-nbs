from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.types import AppointmentStatus, Service
from bx_sch_4_nbs.helpers.authentication import create_access_token, create_attendance_token
from bx_sch_4_nbs.helpers.common import utc_now
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
URL = "/v1/appointments/attendance/confirm"


def check(label: str, ok: bool, detail: object = "") -> None:
    print("OK    " if ok else "ERRO  ", label, detail if not ok else "")


user = User(
    name="Test", last_name="Confirm", email_encrypted="x", email_hash="v" * 64, phone_encrypted="x", phone_hash="w" * 64
)
session.add(user)
policy = session.exec(select(Policy)).first()
session.flush()
assert user.id is not None and policy is not None and policy.id is not None
USER_ID, POLICY_ID = user.id, policy.id
now = utc_now()


def make(hours: float, status=AppointmentStatus.SCHEDULED) -> Appointment:
    appointment = Appointment(
        user_id=USER_ID,
        scheduled_at=now + timedelta(hours=hours),
        status=status,
        service=Service.REMOVAL,
        estimated_price=Decimal(10),
        policy_id=POLICY_ID,
        policies_accepted_at=now,
    )
    session.add(appointment)
    session.flush()
    return appointment


active = make(20)
cancelled = make(20, status=AppointmentStatus.CANCELLED)
session.commit()
deadline = now + timedelta(hours=16)

response = client.post(URL, json={"token": create_attendance_token(active.id, deadline)})  # ty: ignore[invalid-argument-type]
first_confirmation = response.json()["detail"]["attendance_confirmed_at"] if response.status_code == 200 else None
check("token valido confirma (200)", response.status_code == 200 and first_confirmation is not None, response.json())

response = client.post(URL, json={"token": create_attendance_token(active.id, deadline)})  # ty: ignore[invalid-argument-type]
check(
    "confirmar de novo e idempotente (200, mesma data)",
    response.status_code == 200 and response.json()["detail"]["attendance_confirmed_at"] == first_confirmation,
    response.json(),
)

response = client.post(URL, json={"token": create_attendance_token(active.id, now - timedelta(minutes=1))})  # ty: ignore[invalid-argument-type]
check("token expirado (400)", response.status_code == 400, response.status_code)

response = client.post(URL, json={"token": create_access_token(user)})
check("token de login no lugar do de confirmacao (400)", response.status_code == 400, response.status_code)

response = client.post(URL, json={"token": create_attendance_token(cancelled.id, deadline)})  # ty: ignore[invalid-argument-type]
check("marcacao cancelada (409)", response.status_code == 409, response.status_code)

response = client.post(URL, json={"token": create_attendance_token(999999, deadline)})
check("marcacao que nao existe (404)", response.status_code == 404, response.status_code)

transaction.rollback()
connection.close()
