from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.routers.schemas.types import StudioDatetime

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


class MonthPublish(BaseModel):
    year: int = Field(ge=2026, le=2100)
    month: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def validate_not_past(self) -> MonthPublish:
        today = to_studio_time(utc_now()).date()
        if (self.year, self.month) < (today.year, today.month):
            raise ValueError("Cannot publish a month in the past.")
        return self


class PublishedMonthResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    published_at: StudioDatetime


class MonthPublished(PublishedMonthResult):
    notified_clients: int
