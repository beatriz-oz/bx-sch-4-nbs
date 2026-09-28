from datetime import date, time

from pydantic import BaseModel, ConfigDict, field_validator

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now

MONDAY = 0


class ScheduleExceptionSet(BaseModel):
    day: date
    slot_time: time | None = None
    is_open: bool

    @field_validator("day")
    @classmethod
    def validate_day(cls, value: date) -> date:
        if value.weekday() == MONDAY:
            raise ValueError("Mondays are always closed to clients.")
        if value < to_studio_time(utc_now()).date():
            raise ValueError("The day is in the past.")
        return value

    @field_validator("slot_time")
    @classmethod
    def validate_slot_time(cls, value: time | None) -> time | None:
        if value is not None and value not in settings.appointment_slots:
            raise ValueError("Invalid slot time.")
        return value


class ScheduleExceptionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    slot_time: time | None
    is_open: bool
