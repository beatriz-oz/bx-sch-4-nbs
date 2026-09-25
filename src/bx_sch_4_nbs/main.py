from fastapi import APIRouter, FastAPI

from bx_sch_4_nbs.routers.admin import router as admin_router
from bx_sch_4_nbs.routers.auth import router as auth_router
from bx_sch_4_nbs.routers.exceptions import setup_exception_handlers

app = FastAPI(title="Nail Scheduling API")
setup_exception_handlers(app)

router = APIRouter()
router.include_router(admin_router)
router.include_router(auth_router)

app.include_router(prefix="/v1", router=router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
