from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import AddonPrice, Appointment, NailArtPrice, Policy, ServicePrice, User
from bx_sch_4_nbs.database.queries.prices import estimate_price
from bx_sch_4_nbs.database.types import (
    Addon,
    AppointmentStatus,
    CancellationReason,
    NailArtLevel,
    NailSize,
    Service,
    UserRole,
)
from bx_sch_4_nbs.helpers.authentication import create_access_token
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


def check(label: str, ok: bool, detail: object = "") -> None:
    print("OK    " if ok else "ERRO  ", label, detail if not ok else "")


admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
ana = User(
    name="Ana",
    last_name="Outcome",
    instagram="ana.outcome",
    email_encrypted="x",
    email_hash="o" * 64,
    phone_encrypted="x",
    phone_hash="p" * 64,
)
session.add(ana)
policy = session.exec(select(Policy)).first()
session.flush()
assert admin is not None and ana.id is not None and policy is not None and policy.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
CLIENT = {"Authorization": f"Bearer {create_access_token(ana)}"}
ANA, POLICY = ana.id, policy.id
now = utc_now()


def price_of(model: Any, key: Any) -> Decimal:
    row = session.get(model, key)
    assert row is not None
    return row.amount


def service_price(service: Service, nail_size: NailSize | None) -> Decimal:
    row = session.exec(
        select(ServicePrice).where(ServicePrice.service == service, ServicePrice.nail_size == nail_size)
    ).first()
    assert row is not None
    return row.amount


def make(hours: float, status: AppointmentStatus = AppointmentStatus.SCHEDULED, **fields: Any) -> int:
    values: dict[str, Any] = {
        "service": Service.APPLICATION,
        "nail_size": NailSize.MEDIUM,
        "nail_art_level": NailArtLevel.LEVEL_1,
        "broken_nails": 1,
    }
    values.update(fields)
    appointment = Appointment(
        user_id=ANA,
        scheduled_at=now + timedelta(hours=hours),
        status=status,
        estimated_price=Decimal(40),
        policy_id=POLICY,
        policies_accepted_at=now,
        **values,
    )
    session.add(appointment)
    session.flush()
    assert appointment.id is not None
    return appointment.id


scheduled_past = make(-3)
confirmed_past = make(-2, status=AppointmentStatus.CONFIRMED, deposit_paid_at=now - timedelta(days=5))
future = make(48)
cancelled = make(-5, status=AppointmentStatus.CANCELLED, cancellation_reason=CancellationReason.BY_STUDIO)
removal = make(-4, service=Service.REMOVAL, nail_size=None, nail_art_level=None, broken_nails=0)
session.commit()


def post(path: str, body: dict | None = None, headers: dict[str, str] = ADMIN):
    return client.post(f"/v1/admin/appointments/{path}", json=body, headers=headers)


def detail_of(response) -> dict:
    return response.json().get("detail", {}) if response.status_code == 200 else {}


# --- recalcular (nao grava nada) ---
broken = price_of(AddonPrice, Addon.BROKEN_NAIL)
charm = price_of(AddonPrice, Addon.EXTRA_CHARM)
base = service_price(Service.APPLICATION, NailSize.MEDIUM)

response = post(f"{confirmed_past}/estimate", {})
check("recalcular sem mudar nada: 200", response.status_code == 200, response.text[:200])
check(
    "sem mudancas = preco da marcacao com a tabela atual",
    Decimal(str(detail_of(response).get("price"))) == base + price_of(NailArtPrice, NailArtLevel.LEVEL_1) + broken,
    detail_of(response),
)

response = post(
    f"{confirmed_past}/estimate",
    {"nail_art_level": "Level 3", "extra_charms": 3, "broken_nails": 2, "complete_removal": True},
)
expected = (
    base + price_of(NailArtPrice, NailArtLevel.LEVEL_3) + broken * 2 + charm * 3 + service_price(Service.REMOVAL, None)
)
check(
    "com art, charms, unhas e remocao", Decimal(str(detail_of(response).get("price"))) == expected, response.text[:200]
)
session.expire_all()
saved = session.get(Appointment, confirmed_past)
check("recalcular nao grava o preco", saved is not None and saved.final_price is None)

response = post(f"{removal}/estimate", {"extra_charms": 5})
check(
    "remocao: so o preco da remocao",
    Decimal(str(detail_of(response).get("price"))) == service_price(Service.REMOVAL, None),
    response.text[:200],
)
check("recalcular marcacao que nao existe: 404", post("999999/estimate", {}).status_code == 404)
check("charms negativos: 422", post(f"{confirmed_past}/estimate", {"extra_charms": -1}).status_code == 422)

# --- a estimativa da cliente continua igual depois da refatoracao ---
estimate = estimate_price(
    session,
    user_id=ANA,
    scheduled_at=now + timedelta(days=10),
    service=Service.APPLICATION,
    nail_size=NailSize.MEDIUM,
    nail_art_level=NailArtLevel.LEVEL_1,
    broken_nails=1,
    has_other_professional_nails=True,
)
check(
    "estimate_price da cliente nao soma os extras",
    estimate.estimated_price == base + price_of(NailArtPrice, NailArtLevel.LEVEL_1) + broken
    and len(estimate.possible_extras) == 2,
    estimate,
)

# --- concluir ---
response = post(f"{confirmed_past}/complete", {"final_price": "55.50"})
detail = detail_of(response)
check("concluir CONFIRMED: 200", response.status_code == 200, response.text[:200])
check(
    "status Completed e final_price gravado",
    detail.get("status") == "Completed" and Decimal(str(detail.get("final_price"))) == Decimal("55.50"),
    detail,
)
check("concluir de novo: 409", post(f"{confirmed_past}/complete", {"final_price": "55.50"}).status_code == 409)

response = post(f"{scheduled_past}/complete", {"final_price": "0"})
check("concluir SCHEDULED (pagou tudo na hora), preco zero: 200", response.status_code == 200, response.text[:200])
check("sem sinal pago, nao aparece como atrasada", detail_of(response).get("deposit_overdue") is False)

response = post(f"{future}/complete", {"final_price": "40"})
check("concluir antes do horario: 409", response.status_code == 409, response.text[:200])
print("       mensagem:", response.json().get("detail"))
check("concluir cancelada: 409", post(f"{cancelled}/complete", {"final_price": "40"}).status_code == 409)
check("concluir sem preco: 422", post(f"{removal}/complete", {}).status_code == 422)
check("preco negativo: 422", post(f"{removal}/complete", {"final_price": "-1"}).status_code == 422)
check("preco com 3 casas: 422", post(f"{removal}/complete", {"final_price": "10.555"}).status_code == 422)
check("concluir que nao existe: 404", post("999999/complete", {"final_price": "40"}).status_code == 404)
check("cliente tentando concluir: 403", post(f"{removal}/complete", {"final_price": "40"}, CLIENT).status_code == 403)

# --- falta ---
response = post(f"{removal}/no-show")
detail = detail_of(response)
check("falta: 200 e status No_show", detail.get("status") == "No_show", response.text[:200])
check("falta: sem final_price e sem reembolso", detail.get("final_price") is None and detail.get("refund_due") is False)
check("falta de novo: 409", post(f"{removal}/no-show").status_code == 409)
check("falta antes do horario: 409", post(f"{future}/no-show").status_code == 409)
check("cliente tentando marcar falta: 403", post(f"{future}/no-show", headers=CLIENT).status_code == 403)

transaction.rollback()
connection.close()
