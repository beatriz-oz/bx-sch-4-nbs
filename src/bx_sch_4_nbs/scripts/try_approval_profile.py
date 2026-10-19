# ruff: noqa: DTZ001
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import bx_sch_4_nbs.routers.auth as auth_router
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.types import AppointmentStatus, CancellationReason, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_phone
from bx_sch_4_nbs.main import app

codes: list[str] = []
setattr(auth_router, "send_verification_code", lambda to, code: codes.append(code))  # noqa: B010

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


def make_user(name: str, phone: str, active: bool) -> User:
    email = f"{name.lower()}@approval.test"
    user = User(
        name=name,
        last_name="Test",
        instagram=f"{name.lower()}.approval",
        email_encrypted=encrypt_email(email),
        email_hash=hash_email(email),
        phone_encrypted=encrypt_phone(phone),
        phone_hash=hash_phone(phone),
        is_active=active,
        email_verified=True,
        approved_at=datetime(2026, 1, 1) if active else None,
    )
    session.add(user)
    session.flush()
    return user


admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
policy = session.exec(select(Policy)).first()
first_timer = make_user("Firsttimer", "+351913111111", active=False)
regular = make_user("Regular", "+351913222222", active=True)
assert admin is not None and admin.id is not None and policy is not None and policy.id is not None
assert first_timer.id is not None and regular.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
FIRST = {"Authorization": f"Bearer {create_access_token(first_timer)}"}
REGULAR = {"Authorization": f"Bearer {create_access_token(regular)}"}
F, POLICY = first_timer.id, policy.id
now = utc_now()


def make(user_id: int, hours: float, status: AppointmentStatus, **fields: Any) -> int:
    appointment = Appointment(
        user_id=user_id,
        scheduled_at=(now + timedelta(hours=hours)).replace(second=0),
        status=status,
        service=Service.APPLICATION,
        estimated_price=Decimal(40),
        policy_id=POLICY,
        **fields,
    )
    session.add(appointment)
    session.flush()
    assert appointment.id is not None
    return appointment.id


to_complete = make(F, -3, AppointmentStatus.CONFIRMED)
make(F, -24 * 40, AppointmentStatus.COMPLETED, final_price=Decimal(55), duration_minutes=180)
make(F, -24 * 20, AppointmentStatus.NO_SHOW)
make(F, -24 * 10, AppointmentStatus.CANCELLED, cancellation_reason=CancellationReason.CLIENT_EARLY)
future = make(F, 24 * 7, AppointmentStatus.SCHEDULED)
session.commit()


def activation(phone: str):
    return client.post("/v1/auth/activation/start", json={"phone": phone})


def profile(client_id: int, headers: dict[str, str] = ADMIN):
    return client.get(f"/v1/admin/clients/{client_id}", headers=headers)


# --- without approval she cannot create a password ---
response = activation("+351913111111")
check("ativacao sem aprovacao: 403", response.status_code == 403, response.text[:200])
check(
    "o /me diz que ela ainda nao pode criar senha",
    client.get("/v1/auth/me", headers=FIRST).json()["detail"]["can_create_password"] is False,
)
check(
    "cliente com senha: can_create_password falso",
    client.get("/v1/auth/me", headers=REGULAR).json()["detail"]["can_create_password"] is False,
)

# --- approved when completing her appointment ---
response = client.post(
    f"/v1/admin/appointments/{to_complete}/complete",
    json={"final_price": "45", "duration_minutes": 165, "notes": "Loved the chrome", "approve_client": True},
    headers=ADMIN,
)
detail = response.json().get("detail", {})
check("concluir com 'pode voltar': 200", response.status_code == 200, response.text[:200])
check("a marcacao ja mostra a cliente aprovada", detail.get("client", {}).get("approved") is True, detail.get("client"))
check(
    "o /me passa a permitir criar senha",
    client.get("/v1/auth/me", headers=FIRST).json()["detail"]["can_create_password"] is True,
)
check("ativacao depois de aprovada: 200", activation("+351913111111").status_code == 200)

# --- revoked in the profile ---
response = client.put(f"/v1/admin/clients/{F}/approval", json={"approved": False}, headers=ADMIN)
check(
    "revogar: 200 e aprovada falso",
    response.status_code == 200 and response.json()["detail"]["client"]["approved"] is False,
    response.text[:200],
)
check("ativacao depois de revogada: 403", activation("+351913111111").status_code == 403)
response = client.post(
    "/v1/auth/activation/confirm", json={"phone": "+351913111111", "code": codes[-1], "password": "new-password-1"}
)
check("o codigo pedido antes de revogar nao funciona mais: 400", response.status_code == 400, response.text[:200])
response = client.put(f"/v1/admin/clients/{F}/approval", json={"approved": True}, headers=ADMIN)
check("aprovar de novo pelo perfil", response.json()["detail"]["client"]["approved"] is True)

# --- the profile ---
detail = profile(F).json().get("detail", {})
appointments = detail.get("appointments", [])
check(
    "perfil: 200 com os dados da cliente",
    detail.get("client", {}).get("phone") == "+351913111111",
    detail.get("client"),
)
check(
    "perfil: todas as marcacoes, a mais recente primeiro",
    len(appointments) == 5 and appointments[0]["id"] == future,
    [a["id"] for a in appointments],
)
check(
    "perfil: 2 visitas e o total gasto 55 + 45",
    detail.get("client", {}).get("visits") == 2 and Decimal(str(detail.get("total_spent"))) == Decimal(100),
    detail.get("total_spent"),
)
check("perfil: 1 falta e 1 cancelamento", detail.get("no_shows") == 1 and detail.get("cancellations") == 1)
check("perfil: proxima marcacao preenchida", detail.get("client", {}).get("next_appointment") is not None)
check(
    "perfil: notas da conclusao no historico",
    any(a.get("completion_notes") == "Loved the chrome" for a in appointments),
)
check("perfil da admin: 404", profile(admin.id).status_code == 404)
check("perfil que nao existe: 404", profile(999999).status_code == 404)
check("cliente vendo perfil: 403", profile(F, REGULAR).status_code == 403)
check(
    "cliente aprovando: 403",
    client.put(f"/v1/admin/clients/{F}/approval", json={"approved": True}, headers=REGULAR).status_code == 403,
)

transaction.rollback()
connection.close()
