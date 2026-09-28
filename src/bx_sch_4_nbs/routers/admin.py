from fastapi import APIRouter, Depends, status

from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.queries import approved_list as queries
from bx_sch_4_nbs.database.queries import policies, prices
from bx_sch_4_nbs.helpers.authentication import get_current_admin
from bx_sch_4_nbs.routers.schemas.admin import (
    NewPolicy,
    NewPreApprovedInstagram,
    PolicyResult,
    PreApprovedInstagramResult,
)
from bx_sch_4_nbs.routers.schemas.prices import ServicePriceResult, ServicePriceUpdate, AddonPriceUpdate, NailArtPriceUpdate, NailArtPriceResult, AddonPriceResult
from bx_sch_4_nbs.routers.schemas.responses import (
    MessageResponse,
    PolicyResponse,
    PreApprovedInstagramListResponse,
    PreApprovedInstagramResponse,
    ServicePriceResponse, NailArtPriceResponse, AddonPriceResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(get_current_admin)])


@router.get(
    "/pre-approved-instagrams",
    description="List all pre-approved Instagram handles",
)
def get_pre_approved_instagrams(
    session: DatabaseSession,
) -> PreApprovedInstagramListResponse:
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


@router.post(
    "/policies",
    description="Publish a new version of the booking policies",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Version already exists"}},
)
def publish_policy(session: DatabaseSession, new_policy: NewPolicy) -> PolicyResponse:
    policy = policies.publish_policy(session, new_policy.version, new_policy.content)
    return PolicyResponse(status="OK", detail=PolicyResult.model_validate(policy))


@router.put(
    "/prices/service",
    description="Update the base price of a service (and nail size)",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No price for this service and nail size"}},
)
def update_service_price(session: DatabaseSession, data: ServicePriceUpdate) -> ServicePriceResponse:
    price = prices.update_service_price(session, data.service, data.nail_size, data.amount)
    return ServicePriceResponse(status="OK", detail=ServicePriceResult.model_validate(price))


@router.put(
    "/prices/nail-art",
    description="Update the price of a nail art level",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No price for this nail art level"}},
)
def update_nail_art_price(session: DatabaseSession, data: NailArtPriceUpdate) -> NailArtPriceResponse:
    price = prices.update_nail_art_price(session, data.nail_art_level, data.amount)
    return NailArtPriceResponse(status="OK", detail=NailArtPriceResult.model_validate(price))


@router.put(
    "/prices/addon",
    description="Update the price of an addon (broken nail, extra charm)",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No price for this addon"}},
)
def update_addon_price(session: DatabaseSession, data: AddonPriceUpdate) -> AddonPriceResponse:
    price = prices.update_addon_price(session, data.addon, data.amount)
    return AddonPriceResponse(status="OK", detail=AddonPriceResult.model_validate(price))