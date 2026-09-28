from fastapi import APIRouter

from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.queries import prices
from bx_sch_4_nbs.routers.schemas.prices import (
    AddonPriceResult,
    NailArtPriceResult,
    PriceList,
    ServicePriceResult,
)
from bx_sch_4_nbs.routers.schemas.responses import PriceListResponse

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
