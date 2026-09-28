from itertools import groupby
from typing import Annotated

from fastapi import APIRouter, Query

from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.queries import availability
from bx_sch_4_nbs.database.types import NailSize
from bx_sch_4_nbs.helpers.authentication import CurrentUser
from bx_sch_4_nbs.helpers.common import to_studio_time
from bx_sch_4_nbs.routers.schemas.appointments import AvailableDay
from bx_sch_4_nbs.routers.schemas.responses import AvailabilityResponse

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.get(
    "/availability",
    description="Available slots of a published month, in the studio time zone",
)
def get_availability(
    session: DatabaseSession,
    _: CurrentUser,
    year: Annotated[int, Query(ge=2026, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    nail_size: NailSize | None = None,
) -> AvailabilityResponse:
    slots = [to_studio_time(slot) for slot in availability.available_slots(session, year, month, nail_size)]
    days = [
        AvailableDay(day=day, slots=list(day_slots)) for day, day_slots in groupby(slots, key=lambda slot: slot.date())
    ]
    return AvailabilityResponse(status="OK", detail=days)
