from datetime import date, datetime
from itertools import groupby

from pydantic import BaseModel

from bx_sch_4_nbs.helpers.common import to_studio_time


class AvailableDay(BaseModel):
    day: date
    slots: list[datetime]

    @classmethod
    def from_utc_slots(cls, slots: list[datetime]) -> list[AvailableDay]:
        studio_slots = [to_studio_time(slot) for slot in slots]
        return [
            cls(day=day, slots=list(day_slots))
            for day, day_slots in groupby(studio_slots, key=lambda slot: slot.date())
        ]


class AvailabilityPreview(BaseModel):
    is_published: bool
    days: list[AvailableDay]
