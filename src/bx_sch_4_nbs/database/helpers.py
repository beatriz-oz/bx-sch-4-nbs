from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

from bx_sch_4_nbs.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)


def get_session() -> Generator[Session]:
    db = Session(engine)

    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DatabaseSession = Annotated[Session, Depends(get_session)]
