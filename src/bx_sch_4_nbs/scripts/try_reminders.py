from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.queries.schedule import appointments_needing_reminder
from bx_sch_4_nbs.database.types import AppointmentStatus, Service

NOW = datetime(2030, 1, 10, 12, 0)  # noqa: DTZ001

with engine.connect() as connection:
    transaction = connection.begin()
    session = Session(bind=connection)

    user = User(
        name="Test",
        last_name="Reminder",
        email_encrypted="x",
        email_hash="r" * 64,
        phone_encrypted="x",
        phone_hash="s" * 64,
    )
    session.add(user)
    policy = session.exec(select(Policy)).first()
    session.flush()

    def make(
        label: str,
        hours: float,
        status=AppointmentStatus.SCHEDULED,
        reminded: bool = False,
    ) -> None:
        session.add(
            Appointment(
                user_id=user.id,  # ty: ignore[invalid-argument-type]
                scheduled_at=NOW + timedelta(hours=hours),
                status=status,
                service=Service.REMOVAL,
                estimated_price=Decimal(10),
                policy_id=policy.id,  # ty: ignore[invalid-argument-type, unresolved-attribute]
                policies_accepted_at=NOW,
                reminder_sent_at=NOW if reminded else None,
                notes=label,
            )
        )

    make("SIM: faltam 23h", 23)
    make("SIM: faltam exatamente 24h", 24)
    make(
        "SIM: confirmada (sinal pago), faltam 10h",
        10,
        status=AppointmentStatus.CONFIRMED,
    )
    make("NAO: faltam 25h", 25)
    make("NAO: ja recebeu lembrete", 20, reminded=True)
    make("NAO: cancelada", 20, status=AppointmentStatus.CANCELLED)
    make("NAO: ja aconteceu", -1)
    session.flush()

    found = {a.notes for a in appointments_needing_reminder(session, NOW) if a.user_id == user.id}
    for label in [
        "SIM: faltam 23h",
        "SIM: faltam exatamente 24h",
        "SIM: confirmada (sinal pago), faltam 10h",
        "NAO: faltam 25h",
        "NAO: ja recebeu lembrete",
        "NAO: cancelada",
        "NAO: ja aconteceu",
    ]:
        expected = label.startswith("SIM")
        print("OK    " if (label in found) == expected else "ERRO  ", label)

    transaction.rollback()
