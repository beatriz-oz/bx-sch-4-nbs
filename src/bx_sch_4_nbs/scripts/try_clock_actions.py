from datetime import timedelta
from decimal import Decimal

from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import Appointment, BookedSlot, Policy, User
from bx_sch_4_nbs.database.queries.schedule import mark_reminder_sent
from bx_sch_4_nbs.database.types import AppointmentStatus, Service
from bx_sch_4_nbs.helpers.common import utc_now


def check(label: str, ok: bool) -> None:
    print("OK    " if ok else "ERRO  ", label)


with engine.connect() as connection:
    transaction = connection.begin()
    session = Session(bind=connection)

    user = User(
        name="Test",
        last_name="Clock",
        email_encrypted="x",
        email_hash="k" * 64,
        phone_encrypted="x",
        phone_hash="l" * 64,
    )
    session.add(user)
    policy = session.exec(select(Policy)).first()
    session.flush()
    assert user.id is not None and policy is not None and policy.id is not None
    now = utc_now()

    appointment = Appointment(
        user_id=user.id,
        scheduled_at=now + timedelta(days=400),
        status=AppointmentStatus.SCHEDULED,
        service=Service.REMOVAL,
        estimated_price=Decimal(10),
        policy_id=policy.id,
        policies_accepted_at=now,
    )
    session.add(appointment)
    session.flush()
    assert appointment.id is not None
    session.add(BookedSlot(slot_at=appointment.scheduled_at, appointment_id=appointment.id))
    session.flush()

    mark_reminder_sent(session, appointment, now)
    session.refresh(appointment)
    check("lembrete: reminder_sent_at gravado", appointment.reminder_sent_at == now)

    check("lembrete: a marcacao continua ativa", appointment.status == AppointmentStatus.SCHEDULED)
    check("lembrete: o horario continua ocupado", session.get(BookedSlot, appointment.scheduled_at) is not None)

    transaction.rollback()
