from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.routers.admin import router as admin_router
from bx_sch_4_nbs.routers.auth import router as auth_router
from bx_sch_4_nbs.routers.exceptions import setup_exception_handlers

app = FastAPI(title="Nail Scheduling API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
setup_exception_handlers(app)

router = APIRouter()
router.include_router(admin_router)
router.include_router(auth_router)

app.include_router(prefix="/v1", router=router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
