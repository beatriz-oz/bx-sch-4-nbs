# ruff: noqa: DTZ001
from datetime import date, datetime, time
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, BookedSlot, Policy, PublishedMonth, ScheduleException, User
from bx_sch_4_nbs.database.types import AppointmentStatus, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_utc
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

# March 2031: Monday 3, Tuesday 4, Saturday 8.
session.add(ScheduleException(day=date(2031, 3, 4), slot_time=time(14, 0), is_open=False))
session.add(ScheduleException(day=date(2031, 3, 8), slot_time=None, is_open=True))
session.add(ScheduleException(day=date(2031, 3, 3), slot_time=None, is_open=True))
booked_at = to_utc(datetime(2031, 3, 5, 10, 0))
appointment = Appointment(
    user_id=admin.id,
    scheduled_at=booked_at,
    status=AppointmentStatus.SCHEDULED,
    service=Service.REMOVAL,
    estimated_price=Decimal(10),
    policy_id=policy.id,
)
session.add(appointment)
session.flush()
assert appointment.id is not None
session.add(BookedSlot(slot_at=booked_at, appointment_id=appointment.id))
session.commit()


def agenda(year: int, month: int, headers: dict[str, str] = ADMIN):
    return client.get("/v1/admin/agenda", params={"year": year, "month": month}, headers=headers)


response = agenda(2031, 3)
detail = response.json().get("detail", {})
days = {d["day"]: {s["time"][:5]: (s["is_open"], s["is_booked"]) for s in d["slots"]} for d in detail.get("days", [])}
check("agenda do mes: 200", response.status_code == 200, response.text[:200])
check("31 dias, cada um com os 3 horarios", len(days) == 31 and all(len(s) == 3 for s in days.values()))
check("mes nao publicado: published_at vazio", detail.get("published_at") is None)
check(
    "terca normal: tudo aberto",
    days["2031-03-11"] == {"10:00": (True, False), "14:00": (True, False), "17:00": (True, False)},
)
check(
    "excecao de horario fecha so as 14h",
    days["2031-03-04"]["14:00"] == (False, False) and days["2031-03-04"]["10:00"][0],
)
check("sabado aberto por excecao", all(open_ for open_, _ in days["2031-03-08"].values()))
check("domingo fechado por padrao", not any(open_ for open_, _ in days["2031-03-09"].values()))
check("segunda fechada mesmo com excecao", not any(open_ for open_, _ in days["2031-03-03"].values()))
check("horario marcado aparece como ocupado", days["2031-03-05"]["10:00"] == (True, True))

session.add(PublishedMonth(year=2031, month=3))
session.commit()
check("mes publicado: published_at preenchido", agenda(2031, 3).json()["detail"]["published_at"] is not None)
check("mes invalido: 422", agenda(2031, 13).status_code == 422)
check("sem login: 401", client.get("/v1/admin/agenda", params={"year": 2031, "month": 3}).status_code == 401)

transaction.rollback()
connection.close()
