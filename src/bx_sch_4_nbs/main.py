from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlmodel import Session

from bx_sch_4_nbs.database.helpers import get_session
from bx_sch_4_nbs.routers.exceptions import setup_exception_handlers

app = FastAPI(title="Nail Scheduling API")
setup_exception_handlers(app)

DatabaseSession = Annotated[Session, Depends(get_session)]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database")
def database_health(session: DatabaseSession) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"database": "ok"}
