from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bx_sch_4_nbs.database.database import get_db

app = FastAPI(title="Nail Scheduling API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database")
async def database_health(
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"database": "ok"}
