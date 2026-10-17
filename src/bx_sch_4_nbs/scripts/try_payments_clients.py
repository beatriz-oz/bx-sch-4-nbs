# ruff: noqa: DTZ001
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.types import AppointmentStatus, CancellationReason, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone
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


def make_user(name: str, active: bool, marker: str) -> User:
    user = User(
        name=name,
        last_name="Zz",
        instagram=f"{name.lower()}.zz",
        email_encrypted=encrypt_email(f"{name.lower()}@zz.com"),
        email_hash=marker * 64,
        phone_encrypted=encrypt_phone("+351912000000"),
        phone_hash=marker.upper() * 64,
        is_active=active,
        email_verified=True,
    )
    session.add(user)
    session.flush()
    return user


admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
policy = session.exec(select(Policy)).first()
regular = make_user("Regular", True, "q")
pending = make_user("Pending", False, "w")
quiet = make_user("Quiet", True, "e")
assert admin is not None and policy is not None and policy.id is not None
assert regular.id is not None and pending.id is not None and quiet.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
CLIENT = {"Authorization": f"Bearer {create_access_token(regular)}"}
POLICY = policy.id
now = utc_now()
old = datetime(2020, 1, 1)


def make(user_id: int, days: float, status: AppointmentStatus, minute: int, **fields: Any) -> int:
    values: dict[str, Any] = {"service": Service.REMOVAL}
    values.update(fields)
    appointment = Appointment(
        user_id=user_id,
        scheduled_at=(now + timedelta(days=days)).replace(minute=minute, second=0),
        status=status,
        estimated_price=Decimal(10),
        policy_id=POLICY,
        created_at=old,
        **values,
    )
    session.add(appointment)
    session.flush()
    assert appointment.id is not None
    return appointment.id


R, P = regular.id, pending.id
waiting = make(R, 10, AppointmentStatus.SCHEDULED, 1)
other = make(R, 11, AppointmentStatus.SCHEDULED, 2, service=Service.OTHER, notes="repair")
paid = make(R, 12, AppointmentStatus.CONFIRMED, 3, deposit_paid_at=old)
past_waiting = make(R, -3, AppointmentStatus.SCHEDULED, 4)
done_1 = make(R, -40, AppointmentStatus.COMPLETED, 5)
done_2 = make(R, -10, AppointmentStatus.COMPLETED, 6)
early = make(
    P,
    20,
    AppointmentStatus.CANCELLED,
    7,
    deposit_paid_at=old,
    cancellation_reason=CancellationReason.CLIENT_EARLY,
    cancelled_at=now - timedelta(days=5),
)
late = make(
    P,
    2,
    AppointmentStatus.CANCELLED,
    8,
    deposit_paid_at=old,
    cancellation_reason=CancellationReason.CLIENT_LATE,
    cancelled_at=now - timedelta(days=1),
)
studio_old = make(
    R,
    -35,
    AppointmentStatus.CANCELLED,
    9,
    deposit_paid_at=old,
    cancellation_reason=CancellationReason.BY_STUDIO,
    cancelled_at=now - timedelta(days=40),
)
session.commit()


def payments() -> dict[str, list[int]]:
    detail = client.get("/v1/admin/payments", headers=ADMIN).json()["detail"]
    return {key: [row["id"] for row in rows] for key, rows in detail.items()}


lists = payments()
pending_ids, refund_ids, recent_ids = lists["pending_deposits"], lists["refunds_due"], lists["recent_cancellations"]
check("sinal pendente: a futura sem sinal", waiting in pending_ids)
check("sinal pendente: sem OTHER, sem confirmada, sem passada", not {other, paid, past_waiting} & set(pending_ids))
check("reembolso: cancelada cedo pela cliente e pelo salao", {early, studio_old} <= set(refund_ids))
check("reembolso: a cancelada em cima da hora nao entra", late not in refund_ids)
check(
    "cancelamentos recentes: os dos ultimos 30 dias", {early, late} <= set(recent_ids) and studio_old not in recent_ids
)

response = client.post(f"/v1/admin/appointments/{early}/refund", headers=ADMIN)
detail = response.json().get("detail", {})
check("marcar reembolso feito: 200", response.status_code == 200, response.text[:200])
check(
    "reembolso gravado e deixa de ser devido",
    detail.get("deposit_refunded_at") is not None and detail.get("refund_due") is False,
)
again = client.post(f"/v1/admin/appointments/{early}/refund", headers=ADMIN).json().get("detail", {})
check("marcar de novo: mesma data (idempotente)", again.get("deposit_refunded_at") == detail.get("deposit_refunded_at"))
check("sai da lista de reembolsos", early not in payments()["refunds_due"])
check(
    "cancelada em cima da hora: 409",
    client.post(f"/v1/admin/appointments/{late}/refund", headers=ADMIN).status_code == 409,
)
check("marcacao ativa: 409", client.post(f"/v1/admin/appointments/{paid}/refund", headers=ADMIN).status_code == 409)
check("nao existe: 404", client.post("/v1/admin/appointments/999999/refund", headers=ADMIN).status_code == 404)
check(
    "cliente tentando: 403",
    client.post(f"/v1/admin/appointments/{studio_old}/refund", headers=CLIENT).status_code == 403,
)
check("cliente vendo pagamentos: 403", client.get("/v1/admin/payments", headers=CLIENT).status_code == 403)


def overview(group: str) -> dict[int, dict]:
    response = client.get("/v1/admin/clients/overview", params={"group": group}, headers=ADMIN)
    return {row["id"]: row for row in response.json().get("detail", [])}


registered = overview("registered")
waiting_list = overview("pending")
check("cadastradas: com senha, incluindo quem nunca marcou", {R, quiet.id} <= set(registered) and P not in registered)
check("pendentes: sem senha", P in waiting_list and R not in waiting_list)
row = registered.get(R, {})
check("visitas contam so as concluidas", row.get("visits") == 2, row)
check(
    "ultima visita e a concluida mais recente",
    str(row.get("last_visit", ""))[:10] == str((now - timedelta(days=10)).date()),
    row.get("last_visit"),
)
check(
    "proxima marcacao e a ativa mais proxima",
    str(row.get("next_appointment", ""))[:10] == str((now + timedelta(days=10)).date()),
    row.get("next_appointment"),
)
check("email e telefone legiveis", row.get("email") == "regular@zz.com" and row.get("phone") == "+351912000000")
quiet_row = registered.get(quiet.id, {})
check(
    "quem nunca marcou: 0 visitas, sem datas",
    quiet_row.get("visits") == 0 and quiet_row.get("next_appointment") is None,
)
check("pendente com marcacao so cancelada: sem proxima", waiting_list.get(P, {}).get("next_appointment") is None)
check(
    "grupo invalido: 422",
    client.get("/v1/admin/clients/overview", params={"group": "x"}, headers=ADMIN).status_code == 422,
)
check("cliente vendo a lista: 403", client.get("/v1/admin/clients/overview", headers=CLIENT).status_code == 403)

transaction.rollback()
connection.close()
