from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from bx_sch_4_nbs.database.models import Appointment, User
from bx_sch_4_nbs.database.queries.schedule import is_deposit_overdue, is_refund_due
from bx_sch_4_nbs.database.types import (
    AppointmentStatus,
    CancellationReason,
    NailArtLevel,
    NailSize,
    Service,
)
from bx_sch_4_nbs.routers.schemas.types import InstagramHandle, StudioDatetime


class PreApprovedInstagramResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instagram: str
    created_at: StudioDatetime


class NewPreApprovedInstagram(BaseModel):
    instagram: InstagramHandle


class NewPolicy(BaseModel):
    version: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1)


class PolicyResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: str
    content: str
    published_at: StudioDatetime


class ClientSummary(BaseModel):
    id: int
    name: str
    last_name: str
    instagram: str | None


class AdminAppointmentResult(BaseModel):
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
    final_price: Decimal | None
    created_at: StudioDatetime | None
    cancelled_at: StudioDatetime | None
    cancellation_reason: CancellationReason | None
    client: ClientSummary
    deposit_paid: bool
    attendance_confirmed: bool
    deposit_overdue: bool
    refund_due: bool

    @classmethod
    def from_row(cls, appointment: Appointment, user: User, now: datetime) -> AdminAppointmentResult:
        if appointment.id is None or user.id is None:
            raise RuntimeError("Appointment and user must be saved before listing.")

        deposit_paid: bool = appointment.deposit_paid_at is not None
        attendance_confirmed = appointment.attendance_confirmed_at is not None
        deposit_overdue: bool = is_deposit_overdue(appointment, now)
        refund_due: bool = is_refund_due(appointment)

        client = ClientSummary(
            id=user.id,
            name=user.name,
            last_name=user.last_name,
            instagram=user.instagram,
        )

        return cls(
            id=appointment.id,
            scheduled_at=appointment.scheduled_at,
            status=appointment.status,
            service=appointment.service,
            nail_size=appointment.nail_size,
            nail_art_level=appointment.nail_art_level,
            broken_nails=appointment.broken_nails,
            has_other_professional_nails=appointment.has_other_professional_nails,
            estimated_price=appointment.estimated_price,
            final_price=appointment.final_price,
            created_at=appointment.created_at,
            cancelled_at=appointment.cancelled_at,
            cancellation_reason=appointment.cancellation_reason,
            client=client,
            deposit_paid=deposit_paid,
            attendance_confirmed=attendance_confirmed,
            deposit_overdue=deposit_overdue,
            refund_due=refund_due,
        )


class StudioCancellation(BaseModel):
    message: str | None = Field(default=None, max_length=500)
