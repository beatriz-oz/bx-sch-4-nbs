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
from bx_sch_4_nbs.helpers.common import to_utc, utc_now
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
policy = session.exec(select(Policy)).first()
assert admin is not None and admin.id is not None and policy is not None and policy.id is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
ADMIN_ID, POLICY = admin.id, policy.id
paid = datetime(2031, 1, 1)


def make(when_utc: datetime, status: AppointmentStatus, service: Service = Service.APPLICATION, **fields: Any) -> int:
    appointment = Appointment(
        user_id=ADMIN_ID,
        scheduled_at=when_utc,
        status=status,
        service=service,
        estimated_price=Decimal(45),
        policy_id=POLICY,
        **fields,
    )
    session.add(appointment)
    session.flush()
    assert appointment.id is not None
    return appointment.id


def lisbon(year: int, month: int, day: int, hour: int) -> datetime:
    """A Lisbon wall-clock time, as stored (UTC)."""
    return to_utc(datetime(year, month, day, hour))


# March 2031
make(lisbon(2031, 3, 10, 14), AppointmentStatus.COMPLETED, final_price=Decimal(50), duration_minutes=200)
make(lisbon(2031, 3, 12, 10), AppointmentStatus.COMPLETED, Service.REMOVAL, final_price=Decimal(10))
make(lisbon(2031, 3, 20, 10), AppointmentStatus.NO_SHOW, deposit_paid_at=paid)
make(
    lisbon(2031, 3, 25, 10),
    AppointmentStatus.CANCELLED,
    deposit_paid_at=paid,
    cancellation_reason=CancellationReason.CLIENT_LATE,
)
make(
    lisbon(2031, 3, 26, 10),
    AppointmentStatus.CANCELLED,
    deposit_paid_at=paid,
    cancellation_reason=CancellationReason.CLIENT_EARLY,
)
make(lisbon(2031, 3, 27, 10), AppointmentStatus.CANCELLED, cancellation_reason=CancellationReason.NOT_CONFIRMED)
# 31 March 23:30 UTC is already 1 April 00:30 in Lisbon (summer time): it belongs to April.
make(datetime(2031, 3, 31, 23, 30), AppointmentStatus.COMPLETED, final_price=Decimal(40))
make(lisbon(2031, 3, 28, 10), AppointmentStatus.SCHEDULED)
session.commit()

response = client.get("/v1/admin/reports", params={"year": 2031}, headers=ADMIN)
detail = response.json().get("detail", {})
months = {month["month"]: month for month in detail.get("months", [])}
march, april = months.get(3, {}), months.get(4, {})
check("relatorio do ano: 200 com 12 meses", response.status_code == 200 and len(months) == 12, response.text[:200])
check("valor do sinal vem da configuracao", Decimal(str(detail.get("deposit_amount"))) == Decimal(10))
check("marco: 2 concluidas", march.get("completed") == 2, march)
check(
    "horas: duracao registrada (200) + prevista da remocao (60)",
    march.get("worked_minutes") == 260,
    march.get("worked_minutes"),
)
check("receita dos servicos: 50 + 10", Decimal(str(march.get("services_revenue"))) == Decimal(60))
check(
    "sinais retidos: a falta e o cancelamento tardio (2 x 10)",
    march.get("kept_deposits") == 2 and Decimal(str(march.get("kept_deposits_revenue"))) == Decimal(20),
    march,
)
check("total: 60 + 20", Decimal(str(march.get("total_revenue"))) == Decimal(80))
check("1 falta e 3 cancelamentos", march.get("no_shows") == 1 and march.get("cancellations") == 3)
by_service = {row["service"]: row for row in march.get("by_service", [])}
check(
    "por servico: aplicacao e remocao separadas",
    by_service.get("Application", {}).get("worked_minutes") == 200
    and by_service.get("Removal", {}).get("completed") == 1,
    by_service,
)
check(
    "virada de mes pelo fuso de Lisboa: conta em abril",
    april.get("completed") == 1 and Decimal(str(april.get("total_revenue"))) == Decimal(40),
    april,
)
check(
    "meses vazios com zero",
    months.get(6, {}).get("completed") == 0 and Decimal(str(months.get(6, {}).get("total_revenue"))) == 0,
)

# --- duration recorded at completion ---
now = utc_now()
recorded = make(now - timedelta(hours=5), AppointmentStatus.CONFIRMED)
default = make(now - timedelta(hours=6), AppointmentStatus.CONFIRMED, Service.MAINTENANCE)
invalid = make(now - timedelta(hours=7), AppointmentStatus.CONFIRMED)
session.commit()


def complete(appointment_id: int, body: dict[str, Any]):
    return client.post(f"/v1/admin/appointments/{appointment_id}/complete", json=body, headers=ADMIN)


response = complete(recorded, {"final_price": "50", "duration_minutes": 195, "notes": "  Chrome, loved it  "})
check(
    "concluir com duracao: grava 195",
    response.status_code == 200 and response.json()["detail"]["duration_minutes"] == 195,
    response.text[:200],
)
check(
    "notas da conclusao gravadas (sem espacos sobrando)",
    response.json().get("detail", {}).get("completion_notes") == "Chrome, loved it",
)
response = complete(default, {"final_price": "35"})
check(
    "concluir sem duracao: usa a prevista da manutencao (150)",
    response.json().get("detail", {}).get("duration_minutes") == 150,
    response.text[:200],
)
check("sem notas: fica vazio", response.json().get("detail", {}).get("completion_notes") is None)
check("duracao absurda: 422", complete(invalid, {"final_price": "35", "duration_minutes": 5}).status_code == 422)
check("ano invalido: 422", client.get("/v1/admin/reports", params={"year": 1999}, headers=ADMIN).status_code == 422)
check("sem login: 401", client.get("/v1/admin/reports", params={"year": 2031}).status_code == 401)

transaction.rollback()
connection.close()
