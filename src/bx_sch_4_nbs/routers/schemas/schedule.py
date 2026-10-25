from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class AgendaSlotResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: time
    is_open: bool
    is_booked: bool


class AgendaDay(BaseModel):
    day: date
    slots: list[AgendaSlotResult]
    custom_times: bool


class AgendaMonth(BaseModel):
    year: int
    month: int
    published_at: StudioDatetime | None
    days: list[AgendaDay]


class DaySlotsSet(BaseModel):
    """The slots of one day. An empty list goes back to the default slots."""

    day: date
    slot_times: list[time] = Field(max_length=8)

    @field_validator("day")
    @classmethod
    def validate_day(cls, value: date) -> date:
        if value < to_studio_time(utc_now()).date():
            raise ValueError("The day is in the past.")
        return value

    @field_validator("slot_times")
    @classmethod
    def validate_slot_times(cls, value: list[time]) -> list[time]:
        for slot_time in value:
            if not time(7, 0) <= slot_time <= time(21, 0) or slot_time.minute % 15 or slot_time.second:
                raise ValueError("Slots go from 07:00 to 21:00, in steps of 15 minutes.")
        if len(set(value)) != len(value):
            raise ValueError("The same time appears twice.")
        return sorted(value)
