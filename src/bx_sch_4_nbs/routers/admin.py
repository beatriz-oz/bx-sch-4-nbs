import calendar
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.models import Appointment, User
from bx_sch_4_nbs.database.queries import (
    admin,
    availability,
    policies,
    prices,
    published_months,
    reports,
    schedule,
    users,
)
from bx_sch_4_nbs.database.queries import approved_list as queries
from bx_sch_4_nbs.database.queries.admin import cancel_appointment_by_studio
from bx_sch_4_nbs.database.queries.schedule import list_appointments
from bx_sch_4_nbs.database.types import AppointmentStatus, NailSize, Service
from bx_sch_4_nbs.helpers.authentication import CurrentAdmin, get_current_admin
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.helpers.email import (
    booking_details,
    send_agenda_published,
    send_booked_by_studio_notification,
    send_cancelled_by_studio_notification,
    send_deposit_confirmation,
)
from bx_sch_4_nbs.helpers.security import decrypt_email, decrypt_phone
from bx_sch_4_nbs.routers.schemas.admin import (
    AdminAppointmentResult,
    AdminPayments,
    AppointmentCompletion,
    ClientOverview,
    ClientResult,
    FinalPriceDetails,
    FinalPriceEstimate,
    MonthReportResult,
    NewPolicy,
    NewPreApprovedInstagram,
    PolicyResult,
    PreApprovedInstagramResult,
    ServiceReport,
    StudioAppointment,
    StudioCancellation,
    YearReport,
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
    AdminPaymentsResponse,
    AgendaMonthResponse,
    AvailabilityPreviewResponse,
    ClientListResponse,
    ClientOverviewListResponse,
    FinalPriceEstimateResponse,
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
    YearReportResponse,
)
from bx_sch_4_nbs.routers.schemas.schedule import (
    AgendaDay,
    AgendaMonth,
    AgendaSlotResult,
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
    "/agenda",
    description=(
        "The standard slots of a month as the clients see them (open or closed, booked or free), "
        "after the weekly rule and the exceptions. Read-only: change it with schedule-exceptions"
    ),
)
def get_agenda(
    session: DatabaseSession,
    year: Annotated[int, Query(ge=2026, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> AgendaMonthResponse:
    published = published_months.get_published_month(session, year, month)
    agenda = availability.month_agenda(session, year, month)
    return AgendaMonthResponse(
        status="OK",
        detail=AgendaMonth(
            year=year,
            month=month,
            published_at=published.published_at if published else None,
            days=[
                AgendaDay(day=day, slots=[AgendaSlotResult.model_validate(slot) for slot in slots])
                for day, slots in agenda.items()
            ],
        ),
    )


@router.get(
    "/availability-preview",
    description="What clients will see for a month, even before it is published",
    status_code=status.HTTP_200_OK,
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


@router.get(
    "/appointments",
    description="Get all appointments within a period",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "The end date must be after the given start date"}
    },
)
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
            to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M"),
        )

    return AdminAppointmentResponse(status="OK", detail=AdminAppointmentResult.from_row(appointment, user, now))


@router.post(
    "/appointments/{appointment_id}/cancel",
    description="Cancels an appointment on behalf of the studio. The client is notified by email",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Appointment does not exist"},
        status.HTTP_409_CONFLICT: {"description": "Appointment is no longer active or has already started"},
    },
)
def cancel_appointment(
    session: DatabaseSession,
    appointment_id: int,
    background_tasks: BackgroundTasks,
    admin: CurrentAdmin,
    data: StudioCancellation | None = None,
) -> AdminAppointmentResponse:
    if admin.id is None:
        raise RuntimeError("Authenticated admin without id.")

    now = utc_now()
    appointment, user = cancel_appointment_by_studio(session, appointment_id, admin.id, now)
    is_deposit_paid = appointment.deposit_paid_at is not None

    background_tasks.add_task(
        send_cancelled_by_studio_notification,
        decrypt_email(user.email_encrypted),
        to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M"),
        is_deposit_paid,
        data.message if data else None,
    )

    return AdminAppointmentResponse(status="OK", detail=AdminAppointmentResult.from_row(appointment, user, now))


@router.post(
    "/appointments/{appointment_id}/estimate",
    description="Recalculates the price with what was actually done. Nothing is saved",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Appointment does not exist"}},
)
def estimate_final_price(
    session: DatabaseSession, appointment_id: int, data: FinalPriceDetails
) -> FinalPriceEstimateResponse:
    service, price = admin.estimate_final_price(
        session,
        appointment_id,
        nail_size=data.nail_size,
        nail_art_level=data.nail_art_level,
        broken_nails=data.broken_nails,
        extra_charms=data.extra_charms,
        complete_removal=data.complete_removal,
    )
    return FinalPriceEstimateResponse(status="OK", detail=FinalPriceEstimate(service=service, price=price))


@router.post(
    "/appointments/{appointment_id}/complete",
    description="Marks a past appointment as completed, with the price actually charged",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Appointment does not exist"},
        status.HTTP_409_CONFLICT: {"description": "Appointment is no longer active or has not started yet"},
    },
)
def complete_appointment(
    session: DatabaseSession, appointment_id: int, data: AppointmentCompletion
) -> AdminAppointmentResponse:
    now = utc_now()
    appointment, user = admin.complete_appointment(
        session, appointment_id, data.final_price, data.duration_minutes, now
    )
    return AdminAppointmentResponse(status="OK", detail=AdminAppointmentResult.from_row(appointment, user, now))


@router.post(
    "/appointments/{appointment_id}/no-show",
    description="Marks a past appointment as a no-show. The deposit, if paid, is not refunded",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Appointment does not exist"},
        status.HTTP_409_CONFLICT: {"description": "Appointment is no longer active or has not started yet"},
    },
)
def mark_no_show(session: DatabaseSession, appointment_id: int) -> AdminAppointmentResponse:
    now = utc_now()
    appointment, user = admin.mark_no_show(session, appointment_id, now)
    return AdminAppointmentResponse(status="OK", detail=AdminAppointmentResult.from_row(appointment, user, now))


@router.get("/clients", description="Search clients by name, Instagram, exact email or exact phone")
def search_clients(
    session: DatabaseSession,
    search: Annotated[str, Query(min_length=2, max_length=255)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ClientListResponse:
    results = []
    for user in admin.search_clients(session, search, limit):
        if user.id is None:
            raise RuntimeError("Client without id.")
        results.append(
            ClientResult(
                id=user.id,
                name=user.name,
                last_name=user.last_name,
                instagram=user.instagram,
                email=decrypt_email(user.email_encrypted),
                phone=decrypt_phone(user.phone_encrypted),
                is_active=user.is_active,
            )
        )
    return ClientListResponse(status="OK", detail=results)


@router.post(
    "/appointments",
    description=(
        "Book an appointment for a client at any day and time (past included). "
        "Send user_id for an existing client, or new_client to register a temporary one"
    ),
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Client does not exist"},
        status.HTTP_409_CONFLICT: {"description": "Time already booked, client already registered, or no policy"},
    },
)
def book_appointment(
    session: DatabaseSession, data: StudioAppointment, background_tasks: BackgroundTasks
) -> AdminAppointmentResponse:
    current_policy = policies.get_current_policy(session)
    if current_policy is None or current_policy.id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No booking policy is published yet.")

    if data.user_id is not None:
        client = admin.get_client(session, data.user_id)
    elif data.new_client is not None:
        client = users.create_first_time_user(
            session,
            instagram=data.new_client.instagram,
            name=data.new_client.name,
            last_name=data.new_client.last_name,
            email=data.new_client.email,
            phone=data.new_client.phone,
        )
    else:
        raise RuntimeError("StudioAppointment must have user_id or new_client.")

    if client.id is None:
        raise RuntimeError("Client without id.")

    now = utc_now()
    appointment = admin.book_appointment_by_studio(
        session,
        user_id=client.id,
        scheduled_at=data.scheduled_at,
        service=data.service,
        nail_size=data.nail_size,
        nail_art_level=data.nail_art_level,
        broken_nails=data.broken_nails,
        has_other_professional_nails=data.has_other_professional_nails,
        estimated_price=data.estimated_price,
        notes=data.notes,
        policy_id=current_policy.id,
        now=now,
    )

    # Squeeze-ins and past bookings get no email: the manicure has just talked to the client.
    if not admin.is_within_reminder_window(appointment.scheduled_at, now):
        background_tasks.add_task(
            send_booked_by_studio_notification,
            decrypt_email(client.email_encrypted),
            to_studio_time(appointment.scheduled_at).strftime("%d/%m/%Y %H:%M"),
            booking_details(appointment),
            appointment.service != Service.OTHER,
        )

    return AdminAppointmentResponse(status="OK", detail=AdminAppointmentResult.from_row(appointment, client, now))


@router.get(
    "/payments", description="Pending deposits, refunds still to make and the cancellations of the last 30 days"
)
def get_payments(session: DatabaseSession) -> AdminPaymentsResponse:
    now = utc_now()

    def results(rows: list[tuple[Appointment, User]]) -> list[AdminAppointmentResult]:
        return [AdminAppointmentResult.from_row(appointment, user, now) for appointment, user in rows]

    return AdminPaymentsResponse(
        status="OK",
        detail=AdminPayments(
            pending_deposits=results(admin.pending_deposits(session, now)),
            refunds_due=results(admin.refunds_due(session)),
            recent_cancellations=results(admin.recent_cancellations(session, now)),
        ),
    )


@router.post(
    "/appointments/{appointment_id}/refund",
    description="Records that the studio gave the deposit back. Safe to repeat",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Appointment does not exist"},
        status.HTTP_409_CONFLICT: {"description": "No refund is due for this appointment"},
    },
)
def mark_deposit_refunded(session: DatabaseSession, appointment_id: int) -> AdminAppointmentResponse:
    now = utc_now()
    appointment, user = admin.mark_deposit_refunded(session, appointment_id, now)
    return AdminAppointmentResponse(status="OK", detail=AdminAppointmentResult.from_row(appointment, user, now))


@router.get(
    "/clients/overview",
    description="All clients: registered (with password) or pending (without), with their visits",
)
def get_clients_overview(
    session: DatabaseSession, group: Literal["registered", "pending"] = "registered"
) -> ClientOverviewListResponse:
    rows = admin.clients_overview(session, registered=group == "registered", now=utc_now())
    results = []
    for user, visits, last_visit, next_appointment in rows:
        if user.id is None:
            raise RuntimeError("Client without id.")
        results.append(
            ClientOverview(
                id=user.id,
                name=user.name,
                last_name=user.last_name,
                instagram=user.instagram,
                email=decrypt_email(user.email_encrypted),
                phone=decrypt_phone(user.phone_encrypted),
                is_active=user.is_active,
                email_verified=user.email_verified,
                created_at=user.created_at,
                visits=visits,
                last_visit=last_visit,
                next_appointment=next_appointment,
            )
        )
    return ClientOverviewListResponse(status="OK", detail=results)


@router.get(
    "/reports",
    description="Month by month in a year (Lisbon time): completed appointments, hours worked and income",
)
def get_year_report(session: DatabaseSession, year: Annotated[int, Query(ge=2026, le=2100)]) -> YearReportResponse:
    months = [
        MonthReportResult(
            month=report.month,
            completed=report.completed,
            worked_minutes=report.worked_minutes,
            services_revenue=report.services_revenue,
            kept_deposits=report.kept_deposits,
            kept_deposits_revenue=report.kept_deposits_revenue,
            total_revenue=report.total_revenue,
            no_shows=report.no_shows,
            cancellations=report.cancellations,
            by_service=[
                ServiceReport(
                    service=service,
                    completed=totals.completed,
                    worked_minutes=totals.worked_minutes,
                    revenue=totals.revenue,
                )
                for service, totals in report.by_service.items()
            ],
        )
        for report in reports.year_report(session, year)
    ]
    return YearReportResponse(
        status="OK", detail=YearReport(year=year, deposit_amount=settings.deposit_amount, months=months)
    )
