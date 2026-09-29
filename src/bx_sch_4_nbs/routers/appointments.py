from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.models import Appointment
from bx_sch_4_nbs.database.queries import availability, policies, prices, schedule
from bx_sch_4_nbs.database.types import NailSize
from bx_sch_4_nbs.helpers.authentication import CurrentUser
from bx_sch_4_nbs.helpers.common import to_studio_time
from bx_sch_4_nbs.helpers.email import (
    send_cancelled_appointment_notification,
    send_cancelled_appointment_notification_client,
    send_new_appointment_notification,
)
from bx_sch_4_nbs.helpers.security import decrypt_email
from bx_sch_4_nbs.routers.schemas.appointments import (
    AppointmentDetails,
    AppointmentResult,
    AvailableDay,
    BookingResult,
    CancellationRequest,
    CancellationResult,
    EstimateResult,
    NewAppointment,
    PossibleExtraResult,
)
from bx_sch_4_nbs.routers.schemas.responses import (
    AvailabilityResponse,
    CancellationResponse,
    EstimateResponse,
    NewAppointmentResponse,
)

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _booking_details(appointment: Appointment) -> str:
    lines = [f"Service: {appointment.service.value}"]
    if appointment.nail_size is not None:
        lines.append(f"Nail size: {appointment.nail_size.value}")
    if appointment.nail_art_level is not None:
        lines.append(f"Nail art: {appointment.nail_art_level.value}")
    if appointment.broken_nails:
        lines.append(f"Broken nails: {appointment.broken_nails}")
    if appointment.has_other_professional_nails:
        lines.append("Nails from another professional: complete removal needed")
    lines.append(f"Estimated price: {appointment.estimated_price} €")
    return "\n".join(lines)


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
    slots = availability.available_slots(session, year, month, nail_size)
    return AvailabilityResponse(status="OK", detail=AvailableDay.from_utc_slots(slots))


@router.post("/estimate", description="Estimated price for an appointment, with possible extras")
def estimate(session: DatabaseSession, user: CurrentUser, data: AppointmentDetails) -> EstimateResponse:
    if user.id is None:
        raise RuntimeError("Authenticated user without id.")

    result = prices.estimate_price(
        session,
        user_id=user.id,
        scheduled_at=data.scheduled_at,
        service=data.service,
        nail_size=data.nail_size,
        nail_art_level=data.nail_art_level,
        broken_nails=data.broken_nails,
        has_other_professional_nails=data.has_other_professional_nails,
    )
    return EstimateResponse(status="OK", detail=EstimateResult.model_validate(result))


@router.post(
    "/{appointment_id}/cancel",
    description="Cancel one of your appointments. Within 48h, accept_deposit_loss must be true.",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Appointment not found"},
        status.HTTP_409_CONFLICT: {"description": "Not cancellable, or deposit loss not accepted"},
    },
)
def cancel_appointment(
    session: DatabaseSession,
    user: CurrentUser,
    appointment_id: int,
    background_tasks: BackgroundTasks,
    data: CancellationRequest | None = None,
) -> CancellationResponse:
    if user.id is None:
        raise RuntimeError("Authenticated user without id.")

    accept_deposit_loss = data.accept_deposit_loss if data is not None else False
    appointment = schedule.cancel_appointment(session, appointment_id, user.id, accept_deposit_loss)

    refund_due = schedule.is_refund_due(appointment)
    deposit_paid = appointment.deposit_paid_at is not None
    when = to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M")

    background_tasks.add_task(
        send_cancelled_appointment_notification_client,
        decrypt_email(user.email_encrypted),
        when,
        deposit_paid,
        refund_due,
    )
    background_tasks.add_task(
        send_cancelled_appointment_notification,
        settings.studio_notification_email,
        user.instagram,
        f"{user.name} {user.last_name}",
        when,
        deposit_paid,
        refund_due,
    )

    return CancellationResponse(
        status="OK",
        detail=CancellationResult(
            appointment=AppointmentResult.model_validate(appointment),
            deposit_refund_due=refund_due,
        ),
    )


@router.post(
    "",
    description="Book an appointment",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Policies changed, or slot not available"}},
)
def create_new_appointment(
    session: DatabaseSession,
    user: CurrentUser,
    data: NewAppointment,
    background_tasks: BackgroundTasks,
) -> NewAppointmentResponse:
    if user.id is None:
        raise RuntimeError("Authenticated user without id.")

    current_policy = policies.get_current_policy(session)
    if current_policy is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No booking policy is published yet. Please contact the studio.",
        )
    if data.policy_id != current_policy.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The policies have changed. Please read them again before booking.",
        )

    if not availability.is_slot_available(session, data.scheduled_at, data.nail_size):
        raise HTTPException(status.HTTP_409_CONFLICT, "This slot is not available.")

    estimate = prices.estimate_price(
        session,
        user_id=user.id,
        scheduled_at=data.scheduled_at,
        service=data.service,
        nail_size=data.nail_size,
        nail_art_level=data.nail_art_level,
        broken_nails=data.broken_nails,
        has_other_professional_nails=data.has_other_professional_nails,
    )

    appointment = schedule.create_appointment(
        session,
        user_id=user.id,
        scheduled_at=data.scheduled_at,
        service=estimate.service,
        nail_size=data.nail_size,
        nail_art_level=data.nail_art_level,
        broken_nails=data.broken_nails,
        has_other_professional_nails=data.has_other_professional_nails,
        estimated_price=estimate.estimated_price,
        policy_id=current_policy.id,
    )

    background_tasks.add_task(
        send_new_appointment_notification,
        settings.studio_notification_email,
        user.instagram,
        f"{user.name} {user.last_name}",
        to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M"),
        _booking_details(appointment),
    )

    return NewAppointmentResponse(
        status="OK",
        detail=BookingResult(
            appointment=AppointmentResult.model_validate(appointment),
            possible_extras=[PossibleExtraResult.model_validate(extra) for extra in estimate.possible_extras],
            note=estimate.note,
        ),
    )
