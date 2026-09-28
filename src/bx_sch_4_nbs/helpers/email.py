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
