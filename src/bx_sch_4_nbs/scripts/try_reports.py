# ruff: noqa: DTZ001
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Expense, Policy, User
from bx_sch_4_nbs.database.types import (
    AppointmentStatus,
    CancellationReason,
    ExpenseCategory,
    Service,
    TradeItem,
    UserRole,
)
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_utc, utc_now
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


# --- clientes, dias trabalhados e medias (2032, um ano so para isto) ---
def make_client(name: str, phone: str) -> int:
    user = User(
        name=name,
        last_name="Report",
        email_encrypted=encrypt_email(f"{name.lower()}@report.test"),
        email_hash=hash_email(f"{name.lower()}@report.test"),
        phone_encrypted=encrypt_phone(phone),
        phone_hash=hash_phone(phone),
    )
    session.add(user)
    session.flush()
    assert user.id is not None
    return user.id


def done(user_id: int, when_utc: datetime, price: int, minutes: int, service: Service = Service.APPLICATION) -> None:
    session.add(
        Appointment(
            user_id=user_id,
            scheduled_at=when_utc,
            status=AppointmentStatus.COMPLETED,
            service=service,
            estimated_price=Decimal(price),
            final_price=Decimal(price),
            duration_minutes=minutes,
            policy_id=POLICY,
            trade_item=TradeItem.NAILS if service == Service.TRADING else None,
        )
    )


ana = make_client("Ana", "+351915333001")
bia = make_client("Bia", "+351915333002")
cris = make_client("Cris", "+351915333003")
done(ana, lisbon(2032, 1, 5, 10), 10, 60, Service.REMOVAL)
done(ana, lisbon(2032, 1, 5, 14), 40, 120)  # a mesma cliente, no mesmo dia
done(ana, lisbon(2032, 1, 20, 10), 50, 180)  # e outra vez no mesmo mes
done(bia, lisbon(2032, 1, 20, 14), 30, 120)  # outra cliente, num dia que ja conta
done(cris, lisbon(2032, 1, 25, 10), 0, 120, Service.TRADING)  # troca: fica de fora
done(ana, lisbon(2032, 2, 3, 10), 40, 120)
session.add(Expense(day=date(2032, 1, 15), description="Geis", category=ExpenseCategory.PRODUCTS, amount=Decimal(30)))
session.commit()

response = client.get("/v1/admin/reports", params={"year": 2032}, headers=ADMIN)
detail = response.json().get("detail", {})
january = detail.get("months", [{}])[0]
totals = detail.get("totals", {})


def money(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


check("janeiro: 2 clientes (a Ana veio 3 vezes, conta 1; a troca nao conta)", january.get("clients") == 2, january)
check("janeiro: 2 dias trabalhados (dia 5 e 20; o dia so com troca nao conta)", january.get("days_worked") == 2)
check("por hora: 130 EUR / 8h = 16.25", money(january.get("revenue_per_hour")) == Decimal("16.25"), january)
check("ganho medio por cliente: 130 / 2 = 65", money(january.get("average_per_client")) == Decimal(65))
check("ganho medio por dia: 130 / 2 = 65", money(january.get("average_per_day")) == Decimal(65))
check("custo por cliente: 30 EUR de despesas / 2 = 15", money(january.get("cost_per_client")) == Decimal(15))
check("lucro por cliente: 65 - 15 = 50", money(january.get("profit_per_client")) == Decimal(50))
march_2032 = detail.get("months", [{}] * 3)[2]
check(
    "mes vazio: sem medias (null, nao 0)",
    march_2032.get("clients") == 0
    and all(
        march_2032.get(key) is None
        for key in ("revenue_per_hour", "average_per_client", "average_per_day", "cost_per_client", "profit_per_client")
    ),
    march_2032,
)
check(
    "ano: 2 clientes e 3 dias (juntados, nao somados: jan 2 + fev 1 clientes daria 3)",
    totals.get("clients") == 2 and totals.get("days_worked") == 3,
    totals,
)
check(
    "ano: 170 EUR em 10h = 17/h, 85 por cliente, 15 de custo e 70 de lucro por cliente",
    money(totals.get("revenue_per_hour")) == Decimal(17)
    and money(totals.get("average_per_client")) == Decimal(85)
    and money(totals.get("cost_per_client")) == Decimal(15)
    and money(totals.get("profit_per_client")) == Decimal(70),
    totals,
)
check(
    "ano: totais de concluidas, horas, receita, despesas e lucro",
    totals.get("completed") == 5
    and totals.get("worked_minutes") == 600
    and money(totals.get("total_revenue")) == Decimal(170)
    and money(totals.get("expenses")) == Decimal(30)
    and money(totals.get("profit")) == Decimal(140)
    and totals.get("trades") == 1,
    totals,
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
