import calendar
import logging
import smtplib
from email.message import EmailMessage

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.models import Appointment
from bx_sch_4_nbs.database.types import Service

logger = logging.getLogger(__name__)


def booking_details(appointment: Appointment) -> str:
    lines = [f"Service: {appointment.service.value}"]
    if appointment.service == Service.OTHER and appointment.notes:
        lines.append(f"Details: {appointment.notes}")
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


def _build_message(to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def send_emails(messages: list[EmailMessage]) -> set[str]:
    failed_emails: set[str] = set()
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            for message in messages:
                try:
                    smtp.send_message(message)
                except smtplib.SMTPException:
                    logger.exception("Failed to send email to %s", message["To"])
                    failed_emails.add(message["To"])
    except OSError, smtplib.SMTPException:
        logger.exception("Error trying to send the emails")
        return {message["To"] for message in messages}

    return failed_emails


def send_email(to: str, subject: str, body: str) -> bool:
    failed_emails = send_emails([_build_message(to, subject, body)])

    return to not in failed_emails


def send_verification_code(to: str, code: str) -> None:
    send_email(
        to=to,
        subject="Your verification code - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"Your verification code is: {code}\n\n"
            "It expires in 10 minutes.\n"
            "If you did not request this code, please ignore this email."
        ),
    )


def send_agenda_published(recipients: list[str], year: int, month: int) -> None:
    if not recipients:
        return

    month_name = f"{calendar.month_name[month]} {year}"
    body = (
        "Hello!\n\n"
        f"The agenda for {month_name} is now open. Book your appointment before the slots run out!\n\n\n\n"
        "You are receiving this email because you are a regular client of Nails by Scooby.\n"
        "If you no longer want to receive these notifications, you can turn them off in your profile."
    )
    send_emails(
        [_build_message(to, f"The agenda for {month_name} is open! - Nails by Scooby", body) for to in recipients]
    )


def send_new_appointment_notification(
    to: str, client_instagram: str | None, client_name: str, when: str, details: str
) -> None:
    instagram_label = f"@{client_instagram}" if client_instagram else "no Instagram"
    send_email(
        to=to,
        subject=f"New appointment: {when} - deposit pending",
        body=(
            f"New appointment from {instagram_label} - {client_name} on {when} (Lisbon time).\n\n"
            f"{details}\n\n"
            "Status: waiting for the deposit."
        ),
    )


def send_cancelled_appointment_notification(
    to: str,
    client_instagram: str | None,
    client_name: str,
    when: str,
    deposit_paid: bool,
    refund_due: bool,
) -> None:
    instagram_label = f"@{client_instagram}" if client_instagram else "no Instagram"

    if refund_due:
        subject = f"CANCELLED: ACTION REQUIRED - {when}"
        deposit_line = "The deposit was paid and must be refunded. Please contact the client to arrange the refund."
    elif not deposit_paid:
        subject = f"CANCELLED - {when}"
        deposit_line = "The deposit had not been paid, so there is nothing to refund."
    else:
        subject = f"CANCELLED - {when}"
        deposit_line = "The appointment was cancelled less than 48 hours before, so the deposit is not refunded."

    send_email(
        to=to,
        subject=subject,
        body=(f"Appointment cancelled by {instagram_label} - {client_name} on {when} (Lisbon time).\n\n{deposit_line}"),
    )


def send_cancelled_appointment_notification_client(to: str, when: str, deposit_paid: bool, refund_due: bool) -> None:
    if refund_due:
        deposit_line = "Your deposit will be refunded. @nailsbyscooby will contact you on Instagram to arrange it."
    elif not deposit_paid:
        deposit_line = "No deposit had been paid for this appointment."
    else:
        deposit_line = "As stated in the booking policies, the deposit is not refunded for cancellations made less than 48 hours before."

    send_email(
        to=to,
        subject="Your appointment has been cancelled - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"Your appointment on {when} (Lisbon time) has been cancelled.\n"
            f"{deposit_line}\n\n"
            "If you did not cancel this appointment, contact @nailsbyscooby on Instagram immediately."
        ),
    )


def send_attendance_reminder(to: str, when: str, deadline: str, token: str) -> bool:
    url = f"{settings.frontend_url}/confirm-attendance?token={token}"
    email_sent = send_email(
        to=to,
        subject="Please confirm your appointment - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"Your appointment is on {when} (Lisbon time). We are looking forward to seeing you!\n\n"
            f"Please confirm your attendance by {deadline} (Lisbon time):\n"
            f"{url}\n\n"
            "If the appointment is not confirmed in time, it will be cancelled and the deposit "
            "will not be refunded.\n\n"
            "If you do not recognize this appointment, contact @nailsbyscooby on Instagram immediately."
        ),
    )
    return email_sent


def send_auto_cancelled_notification_client(to: str, when: str) -> bool:
    return send_email(
        to=to,
        subject="Your appointment has been cancelled - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"Your appointment on {when} (Lisbon time) has been cancelled because the attendance was not "
            f"confirmed at least {settings.confirmation_deadline_hours_before} hours before.\n"
            "As stated in the booking policies, the deposit is not refunded in this case.\n\n"
            "If you have any questions, contact @nailsbyscooby on Instagram."
        ),
    )


def send_auto_cancelled_notification_studio(
    to: str,
    client_instagram: str | None,
    client_name: str,
    when: str,
    deposit_paid: bool,
    email_sent_to_client: bool,
) -> None:
    subject = f"CANCELLED - {when}"
    if not email_sent_to_client:
        subject = f"CANCELLED : ACTION REQUIRED - {when}"

    instagram_label = f"@{client_instagram}" if client_instagram else "no Instagram"
    if deposit_paid:
        deposit_line = "The deposit was paid and is not refunded."
    else:
        deposit_line = "The deposit had not been paid."

    action_text = ""
    if not email_sent_to_client:
        action_text = "The email was not sent. Please, contact the client to warn the auto cancelled appointment!\n\n"

    send_email(
        to=to,
        subject=subject,
        body=(
            f"{action_text}"
            f"Appointment automatically cancelled: {instagram_label} - {client_name} on {when} (Lisbon time).\n\n"
            "Reason: the client did not confirm attendance in time.\n"
            f"{deposit_line}\n"
        ),
    )


def send_deposit_confirmation(to: str, when: str) -> None:
    send_email(
        to=to,
        subject="Your deposit has been received - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"We have received your deposit, and your appointment on {when} (Lisbon time) is confirmed.\n\n"
            f"{settings.reminder_hours_before} hours before the appointment, you will receive an email "
            "asking you to confirm your attendance.\n"
            f"If you need to cancel, please do so more than {settings.free_cancellation_hours} hours before "
            "the appointment to have your deposit refunded, as stated in the booking policies.\n\n"
            "If you did not make this payment, contact @nailsbyscooby on Instagram."
        ),
    )


def send_cancelled_by_studio_notification(to: str, when: str, deposit_paid: bool, message: str | None) -> None:
    message_text = f"Message from Scooby: {message}\n\n" if message else ""
    deposit_status = "Your deposit has been paid and will be refunded."
    if not deposit_paid:
        deposit_status = "Your deposit payment has not been registered, so no actions will be taken."
    send_email(
        to=to,
        subject="Your appointment has been cancelled by the studio - Nails by Scooby",
        body=(
            "Hello, \n\n"
            f"Sorry, but your appointment at {when} needed to be cancelled.\n"
            "If you have any concerns about this, contact @nailsbyscooby on Instagram.\n\n"
            f"{deposit_status}\n\n"
            f"{message_text}"
            f"We would love to see you soon! You can book a new appointment at {settings.frontend_url}."
        ),
    )


def send_booked_by_studio_notification(to: str, when: str, details: str, deposit_required: bool) -> None:
    deposit_line = (
        "To secure your appointment, @nailsbyscooby will contact you on Instagram about the deposit.\n\n"
        if deposit_required
        else ""
    )
    send_email(
        to=to,
        subject=f"Your appointment on {when} - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"Nails by Scooby booked an appointment for you on {when} (Lisbon time).\n\n"
            f"{details}\n\n"
            f"{deposit_line}"
            "Please read our booking policies, they apply to this appointment:\n"
            f"{settings.frontend_url}/policies\n\n"
            "If you do not recognize this appointment, contact @nailsbyscooby on Instagram."
        ),
    )


def send_changed_by_studio_notification(to: str, previous_when: str, when: str, details: str) -> None:
    send_email(
        to=to,
        subject=f"Your appointment was moved to {when} - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"Nails by Scooby moved your appointment from {previous_when} to {when} (Lisbon time).\n\n"
            f"{details}\n\n"
            "You will get a reminder to confirm your attendance before the new date.\n\n"
            "If this does not work for you, contact @nailsbyscooby on Instagram."
        ),
    )


def send_changed_by_client_notification(
    to: str, client_instagram: str | None, client_name: str, previous_when: str, when: str, details: str
) -> None:
    instagram_label = f"@{client_instagram}" if client_instagram else "no Instagram"
    moved = f"moved from {previous_when} to {when}" if previous_when != when else f"on {when}, details changed"
    send_email(
        to=to,
        subject=f"Appointment changed: {when}",
        body=(f"{instagram_label} - {client_name} changed an appointment: {moved} (Lisbon time).\n\nNow:\n{details}"),
    )
