from datetime import date, datetime
from decimal import Decimal
from itertools import groupby
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bx_sch_4_nbs.database.types import AppointmentStatus, NailArtLevel, NailSize, Service
from bx_sch_4_nbs.helpers.common import to_studio_time
from bx_sch_4_nbs.routers.schemas.types import StudioDatetime, UtcDatetime


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


class AppointmentDetails(BaseModel):
    scheduled_at: UtcDatetime
    service: Service
    nail_size: NailSize | None = None
    nail_art_level: NailArtLevel | None = None
    broken_nails: int = Field(default=0, ge=0, le=10)
    has_other_professional_nails: bool = False

    @model_validator(mode="after")
    def validate_service_fields(self) -> AppointmentDetails:
        if self.service == Service.REMOVAL:
            if self.nail_size is not None or self.nail_art_level is not None or self.broken_nails:
                raise ValueError("Removal does not take nail size, nail art level or broken nails.")
        elif self.nail_size is None or self.nail_art_level is None:
            raise ValueError("Nail size and nail art level are required for this service.")
        return self


class PossibleExtraResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    description: str
    amount: Decimal
    per_unit: bool


class EstimateResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service: Service
    estimated_price: Decimal
    possible_extras: list[PossibleExtraResult]
    note: str | None


class NewAppointment(AppointmentDetails):
    policy_id: int
    accept_policies: Literal[True]


class AppointmentResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheduled_at: StudioDatetime
    status: AppointmentStatus
    service: Service
    nail_size: NailSize | None
    nail_art_level: NailArtLevel | None
    broken_nails: int
    has_other_professional_nails: bool
    estimated_price: Decimal
    policies_accepted_at: StudioDatetime


class BookingResult(BaseModel):
    appointment: AppointmentResult
    possible_extras: list[PossibleExtraResult]
    note: str | None
