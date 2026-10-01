from datetime import datetime

from sqlmodel import Session

from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import PublishedMonth
from bx_sch_4_nbs.database.queries.availability import available_slots


def check(label: str, ok: bool) -> None:
    print("OK    " if ok else "ERRO  ", label)


with engine.connect() as connection:
    transaction = connection.begin()
    session = Session(bind=connection)
    session.add(PublishedMonth(year=2030, month=3))
    session.flush()

    # Em março de 2030, antes do horário de verão, Lisboa = UTC. Dia 5 é uma terça-feira.
    now = datetime(2030, 3, 5, 11, 0)
    slots = set(available_slots(session, 2030, 3, now=now))

    check("terca 05/03 14h (faltam 3h): nao aparece", datetime(2030, 3, 5, 14, 0) not in slots)
    check("terca 05/03 17h (faltam 6h): nao aparece", datetime(2030, 3, 5, 17, 0) not in slots)
    check("quarta 06/03 10h (faltam 23h): nao aparece", datetime(2030, 3, 6, 10, 0) not in slots)
    check("quarta 06/03 14h (faltam 27h): aparece", datetime(2030, 3, 6, 14, 0) in slots)
    check("quarta 06/03 17h (faltam 30h): aparece", datetime(2030, 3, 6, 17, 0) in slots)

    exactly_24h = set(available_slots(session, 2030, 3, now=datetime(2030, 3, 5, 10, 0)))
    check("faltando exatamente 24h: nao aparece", datetime(2030, 3, 6, 10, 0) not in exactly_24h)

    transaction.rollback()
