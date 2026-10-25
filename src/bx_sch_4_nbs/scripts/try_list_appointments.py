# ruff: noqa: DTZ001
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.queries.schedule import is_deposit_overdue, list_appointments
from bx_sch_4_nbs.database.types import AppointmentStatus, Service


def check(label: str, ok: bool) -> None:
    print("OK    " if ok else "ERRO  ", label)


with engine.connect() as connection:
    transaction = connection.begin()
    session = Session(bind=connection)

    ana = User(
        name="Ana",
        last_name="List",
        instagram="ana.list",
        email_encrypted="x",
        email_hash="o" * 64,
        phone_encrypted="x",
        phone_hash="p" * 64,
    )
    bia = User(
        name="Bia",
        last_name="List",
        instagram="bia.list",
        email_encrypted="x",
        email_hash="q" * 64,
        phone_encrypted="x",
        phone_hash="r" * 64,
    )
    session.add(ana)
    session.add(bia)
    policy = session.exec(select(Policy)).first()
    session.flush()
    assert ana.id is not None and bia.id is not None and policy is not None and policy.id is not None
    ANA, BIA, POLICY = ana.id, bia.id, policy.id

    def make(user_id: int, when: datetime, status=AppointmentStatus.SCHEDULED, created: datetime | None = None) -> None:
        session.add(
            Appointment(
                user_id=user_id,
                scheduled_at=when,
                status=status,
                service=Service.REMOVAL,
                estimated_price=Decimal(10),
                policy_id=POLICY,
                policies_accepted_at=when,
                created_at=created or datetime(2030, 3, 1),
            )
        )

    # Março de 2030: Lisboa = UTC (antes do horário de verão)
    make(ANA, datetime(2030, 3, 12, 14, 0))
    make(BIA, datetime(2030, 3, 12, 10, 0), status=AppointmentStatus.CONFIRMED)
    make(ANA, datetime(2030, 3, 13, 10, 0), status=AppointmentStatus.CANCELLED)
    make(BIA, datetime(2030, 3, 15, 0, 30))
    make(ANA, datetime(2030, 3, 11, 17, 0))
    session.flush()

    rows = list_appointments(session, date(2030, 3, 12), date(2030, 3, 13))
    times = [appointment.scheduled_at for appointment, _ in rows]
    check("periodo 12 a 13/03: 3 marcacoes", len(rows) == 3)
    check("em ordem de data", times == sorted(times))
    check("cada marcacao vem com a sua cliente", all(user.id == appointment.user_id for appointment, user in rows))
    check("a primeira e a da Bia (10h do dia 12)", rows[0][1].instagram == "bia.list")
    check("o dia 11 ficou de fora", datetime(2030, 3, 11, 17, 0) not in times)
    check("o ultimo dia (13) entrou", datetime(2030, 3, 13, 10, 0) in times)

    only_scheduled = list_appointments(session, date(2030, 3, 1), date(2030, 3, 31), AppointmentStatus.SCHEDULED)
    check(
        "filtro SCHEDULED: so as 3 aguardando sinal",
        len(only_scheduled) == 3 and all(a.status == AppointmentStatus.SCHEDULED for a, _ in only_scheduled),
    )

    now = datetime(2030, 3, 10, 12, 0)
    waiting_3_days = Appointment(
        user_id=ANA,
        scheduled_at=now,
        status=AppointmentStatus.SCHEDULED,
        service=Service.REMOVAL,
        estimated_price=Decimal(10),
        policy_id=POLICY,
        policies_accepted_at=now,
        created_at=now - timedelta(days=3),
    )
    check("sinal pendente ha 3 dias: atrasado", is_deposit_overdue(waiting_3_days, now))
    waiting_3_days.created_at = now - timedelta(days=1)
    check("sinal pendente ha 1 dia: ainda nao", not is_deposit_overdue(waiting_3_days, now))
    waiting_3_days.created_at = now - timedelta(days=3)
    waiting_3_days.status = AppointmentStatus.CONFIRMED
    check("sinal ja pago: nunca atrasado", not is_deposit_overdue(waiting_3_days, now))

    transaction.rollback()
