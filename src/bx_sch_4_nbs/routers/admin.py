from fastapi import APIRouter, Depends, status

from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.queries import approved_list as queries
from bx_sch_4_nbs.helpers.authentication import get_current_admin
from bx_sch_4_nbs.routers.schemas.admin import NewPreApprovedInstagram, PreApprovedInstagramResult
from bx_sch_4_nbs.routers.schemas.responses import (
    MessageResponse,
    PreApprovedInstagramListResponse,
    PreApprovedInstagramResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(get_current_admin)])


@router.get(
    "/pre-approved-instagrams",
    description="List all pre-approved Instagram handles",
)
def get_pre_approved_instagrams(session: DatabaseSession) -> PreApprovedInstagramListResponse:
    entries = queries.list_pre_approved_instagrams(session)
    return PreApprovedInstagramListResponse(
        status="OK",
        detail=[PreApprovedInstagramResult.model_validate(entry) for entry in entries],
    )


@router.post(
    "/pre-approved-instagrams",
    description="Pre-approve an Instagram handle for a first-time booking",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Handle already pre-approved"}},
)
def add_pre_approved_instagram(
    session: DatabaseSession, new_entry: NewPreApprovedInstagram
) -> PreApprovedInstagramResponse:
    entry = queries.create_pre_approved_instagram(session, new_entry.instagram)
    return PreApprovedInstagramResponse(status="OK", detail=PreApprovedInstagramResult.model_validate(entry))


@router.delete(
    "/pre-approved-instagrams/{entry_id}",
    description="Remove a handle from the pre-approved list",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Entry does not exist"}},
)
def remove_pre_approved_instagram(session: DatabaseSession, entry_id: int) -> MessageResponse:
    queries.delete_pre_approved_instagram(session, entry_id)
    return MessageResponse(status="OK", detail="Pre-approved Instagram removed")
