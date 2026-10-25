from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from bx_sch_4_nbs.database.models import Appointment, User
from bx_sch_4_nbs.database.queries.schedule import duration_minutes, is_deposit_overdue, is_refund_due
from bx_sch_4_nbs.database.types import (
    AppointmentStatus,
    CancellationReason,
    ExpenseCategory,
    NailArtLevel,
    NailSize,
    Service,
)
from bx_sch_4_nbs.routers.schemas.types import InstagramHandle, PhoneNumber, StudioDatetime, UtcDatetime


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
    is_active: bool
    approved: bool
    # Admin only: the client's own endpoints never use this schema.
    studio_notes: str | None


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
    notes: str | None
    completion_notes: str | None
    created_at: StudioDatetime | None
    cancelled_at: StudioDatetime | None
    cancellation_reason: CancellationReason | None
    deposit_refunded_at: StudioDatetime | None
    duration_minutes: int
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
            is_active=user.is_active,
            approved=user.approved_at is not None,
            studio_notes=user.studio_notes,
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
            notes=appointment.notes,
            completion_notes=appointment.completion_notes,
            created_at=appointment.created_at,
            cancelled_at=appointment.cancelled_at,
            cancellation_reason=appointment.cancellation_reason,
            deposit_refunded_at=appointment.deposit_refunded_at,
            duration_minutes=duration_minutes(appointment),
            client=client,
            deposit_paid=deposit_paid,
            attendance_confirmed=attendance_confirmed,
            deposit_overdue=deposit_overdue,
            refund_due=refund_due,
        )


class StudioCancellation(BaseModel):
    message: str | None = Field(default=None, max_length=500)


class AppointmentCompletion(BaseModel):
    final_price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    # How long it really took; empty keeps the expected duration of the service.
    duration_minutes: int | None = Field(default=None, ge=15, le=600)
    # A first-time client the studio wants back: she may then create a password.
    approve_client: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class FinalPriceDetails(BaseModel):
    # Empty fields keep what was chosen when booking.
    nail_size: NailSize | None = None
    nail_art_level: NailArtLevel | None = None
    broken_nails: int | None = Field(default=None, ge=0, le=10)
    extra_charms: int = Field(default=0, ge=0, le=50)
    complete_removal: bool = False


class FinalPriceEstimate(BaseModel):
    service: Service
    price: Decimal


class NewClient(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: PhoneNumber
    instagram: InstagramHandle | None = None


class StudioAppointmentDetails(BaseModel):
    """What the studio books or changes. Used as is to change an appointment."""

    # Not based on AppointmentDetails on purpose: the client rules (and the OTHER ban) do not apply here.
    scheduled_at: UtcDatetime
    service: Service
    nail_size: NailSize | None = None
    nail_art_level: NailArtLevel | None = None
    broken_nails: int = Field(default=0, ge=0, le=10)
    has_other_professional_nails: bool = False
    estimated_price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_details(self) -> Self:
        if self.service in (Service.REMOVAL, Service.OTHER):
            if self.nail_size is not None or self.nail_art_level is not None or self.broken_nails:
                raise ValueError(f"{self.service.value} does not take nail size, nail art level or broken nails.")
        elif self.nail_size is None or self.nail_art_level is None:
            raise ValueError("Nail size and nail art level are required for this service.")

        if self.service == Service.OTHER and not (self.notes and self.notes.strip()):
            raise ValueError("Describe the service in notes.")

        # BookedSlot compares exact instants: without this, 13:00:00 and 13:00:30 would not collide.
        self.scheduled_at = self.scheduled_at.replace(second=0, microsecond=0)
        return self


class StudioAppointment(StudioAppointmentDetails):
    user_id: int | None = None
    new_client: NewClient | None = None

    @model_validator(mode="after")
    def validate_client(self) -> Self:
        if (self.user_id is None) == (self.new_client is None):
            raise ValueError("Send either user_id (an existing client) or new_client, not both.")
        return self


class ClientResult(BaseModel):
    id: int
    name: str
    last_name: str
    instagram: str | None
    email: str
    phone: str
    is_active: bool


class AdminPayments(BaseModel):
    pending_deposits: list[AdminAppointmentResult]
    refunds_due: list[AdminAppointmentResult]
    recent_cancellations: list[AdminAppointmentResult]


class ClientOverview(ClientResult):
    email_verified: bool
    approved: bool
    created_at: StudioDatetime | None
    visits: int
    last_visit: StudioDatetime | None
    next_appointment: StudioDatetime | None


class ServiceReport(BaseModel):
    service: Service
    completed: int
    worked_minutes: int
    revenue: Decimal


class CategoryExpenses(BaseModel):
    category: ExpenseCategory
    amount: Decimal


class MonthReportResult(BaseModel):
    month: int
    completed: int
    worked_minutes: int
    services_revenue: Decimal
    kept_deposits: int
    kept_deposits_revenue: Decimal
    total_revenue: Decimal
    no_shows: int
    cancellations: int
    by_service: list[ServiceReport]
    expenses: Decimal
    expenses_by_category: list[CategoryExpenses]
    profit: Decimal


class YearReport(BaseModel):
    year: int
    deposit_amount: Decimal
    months: list[MonthReportResult]


class ClientNotes(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class ClientApproval(BaseModel):
    approved: bool


class ClientProfile(BaseModel):
    client: ClientOverview
    studio_notes: str | None
    total_spent: Decimal
    no_shows: int
    cancellations: int
    appointments: list[AdminAppointmentResult]


class ExpenseSet(BaseModel):
    day: date
    description: str = Field(min_length=1, max_length=200)
    category: ExpenseCategory
    amount: Decimal = Field(gt=0, le=Decimal("99999999.99"), decimal_places=2)

    @model_validator(mode="after")
    def strip_description(self) -> ExpenseSet:
        self.description = self.description.strip()
        if not self.description:
            raise ValueError("The description is empty.")
        return self


class ExpenseResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    description: str
    category: ExpenseCategory
    amount: Decimal
