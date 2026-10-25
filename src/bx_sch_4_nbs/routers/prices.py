from typing import Annotated

from fastapi import APIRouter, Query

from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.queries import prices
from bx_sch_4_nbs.routers.schemas.appointments import EstimateResult, ServiceDetails
from bx_sch_4_nbs.routers.schemas.prices import (
    AddonPriceResult,
    NailArtPriceResult,
    PriceList,
    ServicePriceResult,
)
from bx_sch_4_nbs.routers.schemas.responses import EstimateResponse, PriceListResponse

router = APIRouter(prefix="/prices", tags=["Prices"])


@router.get("", description="Full price list")
def get_prices(session: DatabaseSession) -> PriceListResponse:
    return PriceListResponse(
        status="OK",
        detail=PriceList(
            services=[ServicePriceResult.model_validate(p) for p in prices.list_service_prices(session)],
            nail_art=[NailArtPriceResult.model_validate(p) for p in prices.list_nail_art_prices(session)],
            addons=[AddonPriceResult.model_validate(p) for p in prices.list_addon_prices(session)],
        ),
    )


@router.get(
    "/simulate",
    description=(
        "Public price simulator (no login): the estimated price of a service, with possible extras. "
        "The real estimate, made when booking, also checks the client's last appointment"
    ),
)
def simulate_price(session: DatabaseSession, data: Annotated[ServiceDetails, Query()]) -> EstimateResponse:
    result = prices.simulate_price(
        session,
        service=data.service,
        nail_size=data.nail_size,
        nail_art_level=data.nail_art_level,
        broken_nails=data.broken_nails,
        has_other_professional_nails=data.has_other_professional_nails,
    )
    return EstimateResponse(status="OK", detail=EstimateResult.model_validate(result))
