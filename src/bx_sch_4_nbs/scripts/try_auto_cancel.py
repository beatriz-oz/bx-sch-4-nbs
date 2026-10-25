from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.queries.schedule import appointments_to_auto_cancel
from bx_sch_4_nbs.database.types import AppointmentStatus, Service

NOW = datetime(2030, 1, 10, 12, 0)  # noqa: DTZ001

with engine.connect() as connection:
    transaction = connection.begin()
    session = Session(bind=connection)

    user = User(
        name="Test",
        last_name="AutoCancel",
        email_encrypted="x",
        email_hash="t" * 64,
        phone_encrypted="x",
        phone_hash="u" * 64,
    )
    session.add(user)
    policy = session.exec(select(Policy)).first()
    session.flush()

    def make(
        label: str,
        hours: float,
        status=AppointmentStatus.SCHEDULED,
        reminded: bool = True,
        confirmed: bool = False,
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
                reminder_sent_at=NOW - timedelta(hours=20) if reminded else None,
                attendance_confirmed_at=NOW if confirmed else None,
                notes=label,
            )
        )

    make("SIM: nao confirmou, faltam 3h", 3)
    make("SIM: nao confirmou, faltam exatamente 4h", 4)
    make(
        "SIM: sinal pago mas presenca nao confirmada, faltam 2h",
        2,
        status=AppointmentStatus.CONFIRMED,
    )
    make("NAO: faltam 5h (ainda no prazo)", 5)
    make("NAO: presenca confirmada, faltam 3h", 3, confirmed=True)
    make("NAO: lembrete nunca enviado, faltam 3h", 3, reminded=False)
    make("NAO: ja cancelada", 3, status=AppointmentStatus.CANCELLED)
    make("NAO: ja aconteceu", -1)
    session.flush()

    found = {a.notes for a in appointments_to_auto_cancel(session, NOW) if a.user_id == user.id}
    for label in [
        "SIM: nao confirmou, faltam 3h",
        "SIM: nao confirmou, faltam exatamente 4h",
        "SIM: sinal pago mas presenca nao confirmada, faltam 2h",
        "NAO: faltam 5h (ainda no prazo)",
        "NAO: presenca confirmada, faltam 3h",
        "NAO: lembrete nunca enviado, faltam 3h",
        "NAO: ja cancelada",
        "NAO: ja aconteceu",
    ]:
        expected = label.startswith("SIM")
        print("OK    " if (label in found) == expected else "ERRO  ", label)

    transaction.rollback()
