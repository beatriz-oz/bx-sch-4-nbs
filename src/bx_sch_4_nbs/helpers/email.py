import calendar
import logging
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.models import Appointment
from bx_sch_4_nbs.database.types import STUDIO_ONLY_SERVICES

logger = logging.getLogger(__name__)


def booking_details(appointment: Appointment) -> str:
    lines = [f"Service: {appointment.service.value}"]
    if appointment.service in STUDIO_ONLY_SERVICES and appointment.notes:
        lines.append(f"Details: {appointment.notes}")
    if appointment.nail_size is not None:
        lines.append(f"Nail size: {appointment.nail_size.value}")
    if appointment.nail_art_level is not None:
        lines.append(f"Nail art: {appointment.nail_art_level.value}")
    if appointment.trade_item is not None:
        lines.append(f"Trade: {appointment.trade_item.value}")
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


def studio_address_block() -> str:
    return f"Studio address:\n{settings.studio_address}\n\n{settings.studio_directions}\n\n"


SIGN_OFF = "See you there! 🌸\n\n~Scooby"


def _day_and_time(when: str) -> tuple[str, str]:
    """ "25/11/2026 17:00" -> ("25/11/2026", "17:00")."""
    day, _, hour = when.partition(" ")
    return day, hour


def _deposit_text() -> str:
    amount = settings.deposit_amount
    euros = f"€{amount:.0f}" if amount == amount.to_integral_value() else f"€{amount:.2f}"
    ways = []
    if settings.payment_mbway:
        ways.append(f"via MB Way to {settings.payment_mbway}")
    if settings.payment_revolut:
        ways.append(f"Revolut to {settings.payment_revolut}")
    how = (
        f"You can send it {' or '.join(ways)}."
        if ways
        else "You can send it via MB Way or Revolut: @nailsbyscooby will send you the details on Instagram."
    )
    return (
        f"To confirm your booking, a {euros} deposit is required. {how} The appointment is only confirmed after "
        "receipt of the deposit. Upon registration and receipt of your deposit, you will receive a confirmation email."
    )


def send_booking_received(to: str, when: str) -> None:
    """Right after booking (by the client, or by the studio before the deposit): how to pay the deposit."""
    day, hour = _day_and_time(when)
    send_email(
        to=to,
        subject="Thank you for booking with Nails by Scooby ✨",
        body=(
            "Thank you for booking with Nails by Scooby✨\n\n"
            f"Your appointment has been reserved for {day} at {hour}.\n\n"
            f"{_deposit_text()}\n\n"
            "All information regarding payments and deposit refunds is available in the cancellation policies "
            "provided on Instagram or on the booking platform.\n\n"
            f"{studio_address_block()}"
            f"{SIGN_OFF}"
        ),
    )


def send_appointment_confirmed(to: str, when: str) -> None:
    """The deposit is registered (or the appointment needs none): the appointment is confirmed."""
    day, hour = _day_and_time(when)
    send_email(
        to=to,
        subject="Your appointment is confirmed - Nails by Scooby",
        body=(
            f"Your appointment has been confirmed for {day} at {hour}.\n\n"
            "You can access your client file to change appointment information or cancel it:\n"
            f"{settings.frontend_url}/appointments\n\n"
            f"{studio_address_block()}"
            f"{SIGN_OFF}"
        ),
    )


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


def send_password_reset_code(to: str, code: str) -> None:
    send_email(
        to=to,
        subject="Reset your password - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"Your code to choose a new password is: {code}\n\n"
            "It expires in 10 minutes.\n"
            "If you did not ask to reset your password, ignore this email: your password stays the same."
        ),
    )


def send_password_changed(to: str) -> None:
    send_email(
        to=to,
        subject="Your password was changed - Nails by Scooby",
        body=(
            "Hello!\n\n"
            "The password of your Nails by Scooby account was just changed, "
            "and every other device was logged out.\n\n"
            "If it was you, there is nothing to do.\n"
            'If it was not you, choose a new password with "Forgot your password?" on the login page '
            "and send a message to @nailsbyscooby on Instagram."
        ),
    )


def send_email_change_code(to: str, code: str) -> None:
    send_email(
        to=to,
        subject="Confirm your new email - Nails by Scooby",
        body=(
            "Hello!\n\n"
            "To use this email in your Nails by Scooby account, enter this code on the site:\n\n"
            f"{code}\n\n"
            "It expires in 10 minutes.\n"
            "If you did not ask for this, please ignore this email: nothing changes."
        ),
    )


def send_email_changed(to: str, new_email_masked: str) -> None:
    send_email(
        to=to,
        subject="Your email was changed - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"The email of your Nails by Scooby account was changed to {new_email_masked}. "
            "From now on, our emails go there.\n\n"
            "If it was you, there is nothing to do.\n"
            "If it was not you, send a message to @nailsbyscooby on Instagram immediately."
        ),
    )


def send_phone_changed(to: str, new_phone_masked: str) -> None:
    send_email(
        to=to,
        subject="Your phone number was changed - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"The phone number of your Nails by Scooby account was changed to {new_phone_masked}. "
            "From now on, you log in with this number.\n\n"
            "If it was you, there is nothing to do.\n"
            "If it was not you, send a message to @nailsbyscooby on Instagram immediately."
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


def send_attendance_reminder(to: str, appointment_at: datetime, today: date) -> bool:
    """The day before. appointment_at in Lisbon time; "tomorrow" when it is, the date otherwise."""
    hour = appointment_at.strftime("%H:%M")
    when = (
        f"tomorrow at {hour}"
        if appointment_at.date() == today + timedelta(days=1)
        else f"on {appointment_at:%d/%m/%Y} at {hour}"
    )
    return send_email(
        to=to,
        subject="Your appointment is coming up! ✨",
        body=(
            "Your appointment is coming up! ✨\n\n"
            f"Just a reminder that we have an appointment {when}.\n\n"
            f"{studio_address_block()}"
            f"{SIGN_OFF}"
        ),
    )


def send_deposit_confirmation(to: str, when: str) -> None:
    send_appointment_confirmed(to, when)


def send_booked_by_studio_notification(to: str, when: str, deposit_required: bool, deposit_paid: bool = False) -> None:
    """The studio booked for her: confirmed at once if the deposit is paid or not needed, otherwise how to pay it."""
    if deposit_paid or not deposit_required:
        send_appointment_confirmed(to, when)
    else:
        send_booking_received(to, when)


def send_changed_by_studio_notification(to: str, previous_when: str, when: str, details: str) -> None:
    send_email(
        to=to,
        subject=f"Your appointment was moved to {when} - Nails by Scooby",
        body=(
            "Hello!\n\n"
            f"Nails by Scooby moved your appointment from {previous_when} to {when} (Lisbon time).\n\n"
            f"{details}\n\n"
            f"{studio_address_block()}"
            "You will get a reminder email before the new date.\n\n"
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
