import calendar
import logging
import smtplib
from email.message import EmailMessage

from bx_sch_4_nbs.config import settings

logger = logging.getLogger(__name__)


def _build_message(to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def send_emails(messages: list[EmailMessage]) -> None:
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


def send_email(to: str, subject: str, body: str) -> None:
    send_emails([_build_message(to, subject, body)])


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
    to: str, client_instagram: str | None, client_name: str, when: str, deposit_paid: bool, refund_due: bool
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
        deposit_line = "Your deposit will be refunded. The studio will contact you to arrange it."
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
            "If you did not cancel this appointment, please contact the studio immediately."
        ),
    )
