# ruff: noqa: DTZ001
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import bx_sch_4_nbs.routers.admin as admin_router
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.queries.prices import calculate_price
from bx_sch_4_nbs.database.queries.schedule import appointments_needing_reminder, appointments_to_auto_cancel
from bx_sch_4_nbs.database.types import AppointmentStatus, NailArtLevel, NailSize, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email
from bx_sch_4_nbs.main import app

sent: list[tuple] = []
setattr(admin_router, "send_booked_by_studio_notification", lambda *args: sent.append(args))  # noqa: B010

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
    last_name="Studio",
    instagram="ana.studiobooking",
    email_encrypted=encrypt_email("ana@studio.com"),
    email_hash="b" * 64,
    phone_encrypted="x",
    phone_hash="c" * 64,
)
session.add(ana)
policy = session.exec(select(Policy)).first()
session.flush()
assert admin is not None and admin.id is not None and ana.id is not None
assert policy is not None and policy.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
CLIENT = {"Authorization": f"Bearer {create_access_token(ana)}"}
ANA, ADMIN_ID, POLICY = ana.id, admin.id, policy.id
session.commit()
now = utc_now()


def lisbon(moment: datetime) -> str:
    # The API receives naive times in the studio time zone.
    return to_studio_time(moment).replace(tzinfo=None).isoformat()


def next_monday(days_ahead: int) -> datetime:
    day = to_studio_time(now + timedelta(days=days_ahead))
    while day.weekday() != 0:
        day += timedelta(days=1)
    return day.replace(hour=11, minute=37, second=45, microsecond=0)


def book(body: dict[str, Any], headers: dict[str, str] = ADMIN):
    return client.post("/v1/admin/appointments", json=body, headers=headers)


def detail_of(response) -> dict:
    return response.json().get("detail", {}) if response.status_code == 201 else {}


NEW_CLIENT = {
    "name": "Bia",
    "last_name": "Encaixe",
    "email": "bia.new@client.com",
    "phone": "+351912000111",
}

# --- cliente nova, numa segunda, horario quebrado com segundos ---
monday = next_monday(10)
response = book(
    {
        "scheduled_at": monday.replace(tzinfo=None).isoformat(),
        "service": "Application",
        "nail_size": "XL",
        "nail_art_level": "Level 2",
        "estimated_price": "58.00",
        "new_client": NEW_CLIENT,
    }
)
detail = detail_of(response)
check("cliente nova, segunda-feira, XL as 11:37: 201", response.status_code == 201, response.text[:300])
check(
    "os segundos foram zerados (11:37:00)",
    str(detail.get("scheduled_at", "")).startswith(f"{monday:%Y-%m-%d}T11:37:00"),
    detail.get("scheduled_at"),
)
session.expire_all()
new_user = session.exec(select(User).where(User.name == "Bia", User.last_name == "Encaixe")).first()
check(
    "a cliente nova e temporaria (inativa, sem senha)",
    new_user is not None and not new_user.is_active and new_user.password_hash is None,
)
saved = session.get(Appointment, detail.get("id", 0))
check(
    "politica gravada, sem data de aceite, presenca nao confirmada",
    saved is not None
    and saved.policy_id == policy.id
    and saved.policies_accepted_at is None
    and saved.attendance_confirmed_at is None,
)
check(
    "email de boas-vindas enviado, com aviso do sinal",
    bool(sent) and sent[-1][0] == "bia.new@client.com" and sent[-1][3] is True,
    sent[-1:],
)
check(
    "estado inicial Scheduled e preco digitado",
    detail.get("status") == "Scheduled" and Decimal(str(detail.get("estimated_price"))) == Decimal("58.00"),
)

# --- cliente existente, servico OTHER ---
sent.clear()
far = now + timedelta(days=12)
response = book(
    {
        "scheduled_at": lisbon(far.replace(minute=15, second=0)),
        "service": "Other",
        "estimated_price": "5",
        "notes": "Repair of 1 broken nail",
        "user_id": ANA,
    }
)
detail = detail_of(response)
other_id = detail.get("id", 0)
check("OTHER para cliente existente: 201", response.status_code == 201, response.text[:300])
check("o OTHER guarda a descricao em notes", detail.get("notes") == "Repair of 1 broken nail")
check(
    "email do OTHER sem aviso de sinal",
    bool(sent) and sent[-1][3] is False and "Repair of 1 broken nail" in sent[-1][2],
    sent[-1:],
)

# --- encaixe (daqui a 3 horas) ---
sent.clear()
response = book(
    {
        "scheduled_at": lisbon((now + timedelta(hours=3)).replace(minute=20, second=0)),
        "service": "Removal",
        "estimated_price": "10",
        "user_id": ANA,
    }
)
detail = detail_of(response)
squeeze_id = detail.get("id", 0)
check("encaixe daqui a 3h: 201", response.status_code == 201, response.text[:300])
check("encaixe nasce com a presenca confirmada", detail.get("attendance_confirmed") is True)
check("encaixe nao envia email", sent == [], sent)
later = now + timedelta(hours=2, minutes=30)
check("o lembrete ignora o encaixe", squeeze_id not in [a.id for a in appointments_needing_reminder(session, later)])
check(
    "o auto-cancelamento ignora o encaixe",
    squeeze_id not in [a.id for a in appointments_to_auto_cancel(session, later)],
)

# --- marcacao no passado ---
sent.clear()
response = book(
    {
        "scheduled_at": lisbon((now - timedelta(days=2)).replace(minute=40, second=0)),
        "service": "Removal",
        "estimated_price": "10",
        "user_id": ANA,
    }
)
detail = detail_of(response)
check("marcacao no passado: 201, sem email", response.status_code == 201 and sent == [], response.text[:300])
check("o passado nao fica com presenca confirmada", detail.get("attendance_confirmed") is False)
check(
    "o passado ja pode ser concluido",
    client.post(
        f"/v1/admin/appointments/{detail.get('id')}/complete", json={"final_price": "10"}, headers=ADMIN
    ).status_code
    == 200,
)

# --- erros ---
same_time = {
    "scheduled_at": lisbon(far.replace(minute=15, second=0)),
    "service": "Removal",
    "estimated_price": "10",
    "user_id": ANA,
}
check("mesmo instante de outra marcacao: 409", book(same_time).status_code == 409)
check("user_id e new_client juntos: 422", book({**same_time, "new_client": NEW_CLIENT}).status_code == 422)
check(
    "sem user_id nem new_client: 422", book({k: v for k, v in same_time.items() if k != "user_id"}).status_code == 422
)
check("OTHER sem notes: 422", book({**same_time, "service": "Other"}).status_code == 422)
check(
    "OTHER com tamanho: 422", book({**same_time, "service": "Other", "notes": "x", "nail_size": "M"}).status_code == 422
)
check("aplicacao sem tamanho: 422", book({**same_time, "service": "Application"}).status_code == 422)
check("preco negativo: 422", book({**same_time, "estimated_price": "-1"}).status_code == 422)
duplicated = {**NEW_CLIENT, "email": "other@client.com"}
response = book(
    {**same_time, "scheduled_at": lisbon(far.replace(minute=50, second=0)), "user_id": None, "new_client": duplicated}
)
check("cliente nova com telefone ja cadastrado: 409", response.status_code == 409, response.text[:200])
print("       mensagem:", response.json().get("detail"))
check("user_id que nao existe: 404", book({**same_time, "user_id": 999999}).status_code == 404)
check("user_id da admin: 404", book({**same_time, "user_id": ADMIN_ID}).status_code == 404)
check("cliente tentando usar a rota: 403", book(same_time, CLIENT).status_code == 403)

# --- OTHER do lado da cliente e dos precos ---
client_body = {"scheduled_at": lisbon(far), "service": "Other"}
check(
    "cliente estimando OTHER: 422",
    client.post("/v1/appointments/estimate", json=client_body, headers=CLIENT).status_code == 422,
)
check(
    "cliente marcando OTHER: 422",
    client.post(
        "/v1/appointments", json={**client_body, "policy_id": policy.id, "accept_policies": True}, headers=CLIENT
    ).status_code
    == 422,
)
try:
    calculate_price(session, service=Service.OTHER, nail_size=None, nail_art_level=None)
    check("calculate_price com OTHER levanta ValueError", False)
except ValueError:
    check("calculate_price com OTHER levanta ValueError", True)
check(
    "calculate_price dos outros servicos continua funcionando",
    calculate_price(
        session, service=Service.APPLICATION, nail_size=NailSize.MEDIUM, nail_art_level=NailArtLevel.LEVEL_1
    )
    > 0,
)

response = client.post(
    f"/v1/admin/appointments/{other_id}/estimate", json={"extra_charms": 4, "nail_art_level": "Level 3"}, headers=ADMIN
)
check(
    "recalcular OTHER devolve o preco digitado, ignorando os detalhes",
    response.status_code == 200 and Decimal(str(response.json()["detail"]["price"])) == Decimal(5),
    response.text[:200],
)

# --- sinal atrasado ---
old = datetime(2020, 1, 1)
for service in (Service.OTHER, Service.REMOVAL):
    session.add(
        Appointment(
            user_id=ANA,
            scheduled_at=now + timedelta(days=30, minutes=7 if service == Service.OTHER else 8),
            status=AppointmentStatus.SCHEDULED,
            service=service,
            estimated_price=Decimal(5),
            policy_id=POLICY,
            created_at=old,
            notes="old one",
        )
    )
session.commit()
day = to_studio_time(now + timedelta(days=30)).date().isoformat()
rows = client.get("/v1/admin/appointments", params={"start_date": day, "end_date": day}, headers=ADMIN).json()["detail"]
overdue = {row["service"]: row["deposit_overdue"] for row in rows if row["notes"] == "old one"}
check("OTHER antigo sem sinal nao aparece como atrasado", overdue.get("Other") is False, overdue)
check("remocao antiga sem sinal continua atrasada", overdue.get("Removal") is True, overdue)

transaction.rollback()
connection.close()
