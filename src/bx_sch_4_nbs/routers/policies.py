from fastapi import APIRouter, HTTPException, status

from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.queries import policies
from bx_sch_4_nbs.routers.schemas.admin import PolicyResult
from bx_sch_4_nbs.routers.schemas.responses import PolicyResponse

router = APIRouter(prefix="/policies", tags=["Policies"])


@router.get(
    "/current",
    description="Current booking policies, shown to the client before booking",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No policy published yet"}},
)
def get_current_policy(session: DatabaseSession) -> PolicyResponse:
    policy = policies.get_current_policy(session)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No booking policy has been published yet.")
    return PolicyResponse(status="OK", detail=PolicyResult.model_validate(policy))
