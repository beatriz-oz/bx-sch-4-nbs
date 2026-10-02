# ruff: noqa: DTZ001
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.types import (
    AppointmentStatus,
    CancellationReason,
    Service,
    UserRole,
)
from bx_sch_4_nbs.helpers.authentication import create_access_token
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
ana = User(
    name="Ana",
    last_name="Admin",
    instagram="ana.admin",
    email_encrypted="x",
    email_hash="y" * 64,
    phone_encrypted="x",
    phone_hash="z" * 64,
)
session.add(ana)
policy = session.exec(select(Policy)).first()
session.flush()
assert admin is not None and ana.id is not None and policy is not None and policy.id is not None
ADMIN_TOKEN = {"Authorization": f"Bearer {create_access_token(admin)}"}
CLIENT_TOKEN = {"Authorization": f"Bearer {create_access_token(ana)}"}
ANA, POLICY = ana.id, policy.id
old = datetime(2020, 1, 1)


def make(day: int, status=AppointmentStatus.SCHEDULED, **fields: Any) -> None:
    when = datetime(2030, 3, day, 14, 0)
    session.add(
        Appointment(
            user_id=ANA,
            scheduled_at=when,
            status=status,
            service=Service.REMOVAL,
            estimated_price=Decimal(10),
            policy_id=POLICY,
            policies_accepted_at=when,
            **fields,
        )
    )


make(12, created_at=old)
make(
    13,
    status=AppointmentStatus.CONFIRMED,
    deposit_paid_at=old,
    attendance_confirmed_at=old,
    created_at=old,
)
make(
    14,
    status=AppointmentStatus.CANCELLED,
    deposit_paid_at=old,
    created_at=old,
    cancellation_reason=CancellationReason.CLIENT_EARLY,
    cancelled_at=old,
)
session.commit()

URL = "/v1/admin/appointments"
response = client.get(
    URL,
    params={"start_date": "2030-03-01", "end_date": "2030-03-31"},
    headers=ADMIN_TOKEN,
)
check("listagem do mes: 200", response.status_code == 200, response.json())
rows = {row["scheduled_at"][:10]: row for row in response.json().get("detail", [])}

first = rows.get("2030-03-12", {})
check(
    "a cliente vem aninhada, com o @",
    first.get("client", {}).get("instagram") == "ana.admin",
    first,
)
check(
    "horario no fuso de Lisboa",
    first.get("scheduled_at") == "2030-03-12T14:00:00Z" or str(first.get("scheduled_at")).endswith("+00:00"),
    first.get("scheduled_at"),
)
check(
    "12/03: sinal pendente ha muito tempo -> deposit_overdue",
    first.get("deposit_overdue") is True,
)
check("12/03: deposit_paid falso", first.get("deposit_paid") is False)

second = rows.get("2030-03-13", {})
check(
    "13/03: sinal pago e presenca confirmada",
    second.get("deposit_paid") is True and second.get("attendance_confirmed") is True,
    second,
)
check("13/03: confirmada nao fica atrasada", second.get("deposit_overdue") is False)

third = rows.get("2030-03-14", {})
check(
    "14/03: cancelada cedo com sinal pago -> refund_due",
    third.get("refund_due") is True,
    third,
)

response = client.get(
    URL,
    params={
        "start_date": "2030-03-01",
        "end_date": "2030-03-31",
        "status": "Scheduled",
    },
    headers=ADMIN_TOKEN,
)
check(
    "filtro por status: so a de 12/03",
    len(response.json().get("detail", [])) == 1,
    response.json(),
)

response = client.get(
    URL,
    params={"start_date": "2030-03-31", "end_date": "2030-03-01"},
    headers=ADMIN_TOKEN,
)
check("datas invertidas: 422", response.status_code == 422, response.status_code)

response = client.get(
    URL,
    params={"start_date": "2030-03-01", "end_date": "2030-03-31"},
    headers=CLIENT_TOKEN,
)
check("cliente tentando listar: 403", response.status_code == 403, response.status_code)

transaction.rollback()
connection.close()
