from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from bx_sch_4_nbs.database.exceptions import DuplicateResourceError
from bx_sch_4_nbs.database.models import PublishedMonth


def list_published_months(session: Session) -> list[PublishedMonth]:
    return list(
        session.exec(
            select(PublishedMonth).order_by(col(PublishedMonth.year).desc(), col(PublishedMonth.month).desc())
        ).all()
    )


def publish_month(session: Session, year: int, month: int) -> PublishedMonth:
    entry = PublishedMonth(year=year, month=month)
    session.add(entry)

    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateResourceError(f"{month:02d}/{year} is already published.") from error

    session.refresh(entry)
    return entry
