import calendar
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.queries import (
    admin,
    availability,
    policies,
    prices,
    published_months,
    schedule,
    users,
)
from bx_sch_4_nbs.database.queries import approved_list as queries
from bx_sch_4_nbs.database.queries.schedule import list_appointments
from bx_sch_4_nbs.database.types import AppointmentStatus, NailSize
from bx_sch_4_nbs.helpers.authentication import get_current_admin
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.helpers.email import send_agenda_published, send_deposit_confirmation
from bx_sch_4_nbs.helpers.security import decrypt_email
from bx_sch_4_nbs.routers.schemas.admin import (
    AdminAppointmentResult,
    NewPolicy,
    NewPreApprovedInstagram,
    PolicyResult,
    PreApprovedInstagramResult,
)
from bx_sch_4_nbs.routers.schemas.appointments import AvailabilityPreview, AvailableDay
from bx_sch_4_nbs.routers.schemas.prices import (
    AddonPriceResult,
    AddonPriceUpdate,
    NailArtPriceResult,
    NailArtPriceUpdate,
    ServicePriceResult,
    ServicePriceUpdate,
)
from bx_sch_4_nbs.routers.schemas.responses import (
    AddonPriceResponse,
    AdminAppointmentListResponse,
    AdminAppointmentResponse,
    AvailabilityPreviewResponse,
    MessageResponse,
    MonthPublishedResponse,
    NailArtPriceResponse,
    PolicyResponse,
    PreApprovedInstagramListResponse,
    PreApprovedInstagramResponse,
    PublishedMonthListResponse,
    ScheduleExceptionListResponse,
    ScheduleExceptionResponse,
    ServicePriceResponse,
)
from bx_sch_4_nbs.routers.schemas.schedule import (
    MonthPublish,
    MonthPublished,
    PublishedMonthResult,
    ScheduleExceptionResult,
    ScheduleExceptionSet,
)

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(get_current_admin)])


@router.get(
    "/pre-approved-instagrams",
    description="List all pre-approved Instagram handles",
)
def get_pre_approved_instagrams(
    session: DatabaseSession,
) -> PreApprovedInstagramListResponse:
    entries = queries.list_pre_approved_instagrams(session)
    return PreApprovedInstagramListResponse(
        status="OK",
        detail=[PreApprovedInstagramResult.model_validate(entry) for entry in entries],
    )


@router.post(
    "/pre-approved-instagrams",
    description="Pre-approve an Instagram handle for a first-time booking",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Handle already pre-approved"}},
)
def add_pre_approved_instagram(
    session: DatabaseSession, new_entry: NewPreApprovedInstagram
) -> PreApprovedInstagramResponse:
    entry = queries.create_pre_approved_instagram(session, new_entry.instagram)
    return PreApprovedInstagramResponse(status="OK", detail=PreApprovedInstagramResult.model_validate(entry))


@router.delete(
    "/pre-approved-instagrams/{entry_id}",
    description="Remove a handle from the pre-approved list",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Entry does not exist"}},
)
def remove_pre_approved_instagram(session: DatabaseSession, entry_id: int) -> MessageResponse:
    queries.delete_pre_approved_instagram(session, entry_id)
    return MessageResponse(status="OK", detail="Pre-approved Instagram removed")


@router.post(
    "/policies",
    description="Publish a new version of the booking policies",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Version already exists"}},
)
def publish_policy(session: DatabaseSession, new_policy: NewPolicy) -> PolicyResponse:
    policy = policies.publish_policy(session, new_policy.version, new_policy.content)
    return PolicyResponse(status="OK", detail=PolicyResult.model_validate(policy))


@router.put(
    "/prices/service",
    description="Update the base price of a service (and nail size)",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No price for this service and nail size"}},
)
def update_service_price(session: DatabaseSession, data: ServicePriceUpdate) -> ServicePriceResponse:
    price = prices.update_service_price(session, data.service, data.nail_size, data.amount)
    return ServicePriceResponse(status="OK", detail=ServicePriceResult.model_validate(price))


@router.put(
    "/prices/nail-art",
    description="Update the price of a nail art level",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No price for this nail art level"}},
)
def update_nail_art_price(session: DatabaseSession, data: NailArtPriceUpdate) -> NailArtPriceResponse:
    price = prices.update_nail_art_price(session, data.nail_art_level, data.amount)
    return NailArtPriceResponse(status="OK", detail=NailArtPriceResult.model_validate(price))


@router.put(
    "/prices/addon",
    description="Update the price of an addon (broken nail, extra charm)",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No price for this addon"}},
)
def update_addon_price(session: DatabaseSession, data: AddonPriceUpdate) -> AddonPriceResponse:
    price = prices.update_addon_price(session, data.addon, data.amount)
    return AddonPriceResponse(status="OK", detail=AddonPriceResult.model_validate(price))


@router.get("/schedule-exceptions", description="Schedule exceptions of a month")
def get_schedule_exceptions(
    session: DatabaseSession,
    year: Annotated[int, Query(ge=2026, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> ScheduleExceptionListResponse:
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    entries = schedule.list_exceptions(session, first_day, last_day)
    return ScheduleExceptionListResponse(
        status="OK",
        detail=[ScheduleExceptionResult.model_validate(entry) for entry in entries],
    )


@router.put(
    "/schedule-exceptions",
    description="Open or close a whole day (slot_time empty) or a single slot",
)
def set_schedule_exception(session: DatabaseSession, data: ScheduleExceptionSet) -> ScheduleExceptionResponse:
    entry = schedule.set_exception(session, data.day, data.slot_time, data.is_open)

    warning = None
    if not data.is_open:
        booked = schedule.count_booked_slots(session, data.day, data.slot_time)
        if booked:
            warning = f"{booked} appointment(s) already booked in this period. They were not cancelled automatically."

    return ScheduleExceptionResponse(
        status="OK",
        detail=ScheduleExceptionResult.model_validate(entry),
        warning=warning,
    )


@router.delete(
    "/schedule-exceptions/{exception_id}",
    description="Remove an exception; the day goes back to the weekly default",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Exception does not exist"}},
)
def remove_schedule_exception(session: DatabaseSession, exception_id: int) -> MessageResponse:
    schedule.delete_exception(session, exception_id)
    return MessageResponse(status="OK", detail="Schedule exception removed")


@router.get("/published-months", description="Published months, most recent first")
def get_published_months(session: DatabaseSession) -> PublishedMonthListResponse:
    entries = published_months.list_published_months(session)
    return PublishedMonthListResponse(
        status="OK",
        detail=[PublishedMonthResult.model_validate(entry) for entry in entries],
    )


@router.post(
    "/published-months",
    description="Publish a month's agenda and notify the regular clients by email",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Month already published"}},
)
def publish_month(
    session: DatabaseSession, data: MonthPublish, background_tasks: BackgroundTasks
) -> MonthPublishedResponse:
    entry = published_months.publish_month(session, data.year, data.month)

    if entry.published_at is None:
        raise RuntimeError("published_at should have been set by the database.")

    recipients = [decrypt_email(user.email_encrypted) for user in users.list_agenda_subscribers(session)]
    background_tasks.add_task(send_agenda_published, recipients, data.year, data.month)

    return MonthPublishedResponse(
        status="OK",
        detail=MonthPublished(
            year=entry.year,
            month=entry.month,
            published_at=entry.published_at,
            notified_clients=len(recipients),
        ),
    )


@router.get(
    "/availability-preview",
    description="What clients will see for a month, even before it is published",
)
def get_availability_preview(
    session: DatabaseSession,
    year: Annotated[int, Query(ge=2026, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    nail_size: NailSize | None = None,
) -> AvailabilityPreviewResponse:
    slots = availability.available_slots(session, year, month, nail_size, require_published=False)
    return AvailabilityPreviewResponse(
        status="OK",
        detail=AvailabilityPreview(
            is_published=availability.is_month_published(session, year, month),
            days=AvailableDay.from_utc_slots(slots),
        ),
    )


@router.get("/appointments", description="Get all appointments within a period")
def get_appointments(
    session: DatabaseSession,
    start_date: date,
    end_date: date,
    appointment_status: Annotated[AppointmentStatus | None, Query(alias="status")] = None,
) -> AdminAppointmentListResponse:

    if end_date < start_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The end date must be after the given start date",
        )

    now = utc_now()
    appointments = list_appointments(session, start_date, end_date, appointment_status)

    results = [AdminAppointmentResult.from_row(appointment, user, now) for appointment, user in appointments]

    return AdminAppointmentListResponse(status="OK", detail=results)


@router.post(
    "/appointments/{appointment_id}/deposit",
    description="Confirms that the deposit has been paid. Only the admin can approve this",
)
def confirm_deposit(
    session: DatabaseSession, appointment_id: int, background_tasks: BackgroundTasks
) -> AdminAppointmentResponse:
    now = utc_now()
    appointment, user, is_confirmed = admin.confirm_deposit(session, appointment_id, now)

    if is_confirmed:
        background_tasks.add_task(
            send_deposit_confirmation,
            decrypt_email(user.email_encrypted),
            str(to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M")),
        )

    return AdminAppointmentResponse(status="OK", detail=AdminAppointmentResult.from_row(appointment, user, now))
