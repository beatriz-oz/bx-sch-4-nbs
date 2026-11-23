# ruff: noqa: DTZ001
"""The client emails written by Scooby: booking, confirmation and reminder (and the address in them)."""

from datetime import date, datetime

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.helpers import email

captured: list[tuple[str, str, str]] = []
setattr(email, "send_email", lambda to, subject, body: captured.append((to, subject, body)) or True)  # noqa: B010


def check(label: str, ok: bool, detail: object = "") -> None:
    print("OK    " if ok else "ERRO  ", label, detail if not ok else "")


ADDRESS = "Rua de Passos Manuel 228, 3rd floor, left"
SIGN_OFF = "See you there! 🌸"

# --- Booking ---
setattr(settings, "payment_mbway", "")  # noqa: B010
setattr(settings, "payment_revolut", "")  # noqa: B010
email.send_booking_received("ana@teste.com", "25/11/2026 17:00")
to, subject, body = captured[-1]
check("marcacao: vai para a cliente", to == "ana@teste.com")
check("marcacao: comeca pelo agradecimento", body.startswith("Thank you for booking with Nails by Scooby✨"))
check("marcacao: dia e hora", "reserved for 25/11/2026 at 17:00." in body, body)
check("marcacao: sinal de 10 euros", "a €10 deposit is required" in body, body)
check(
    "marcacao: pede o @ do Instagram na descricao",
    "Write down your instagram @ on the transfer description." in body,
    body,
)
check(
    "marcacao: a confirmacao num paragrafo a parte", "description.\n\nThe appointment is only confirmed" in body, body
)
check("marcacao: sem MB Way/Revolut configurados, aponta para o Instagram", "details on Instagram" in body, body)
check("marcacao: morada e como chegar", ADDRESS in body and "Bolhão" in body and "PR. D. João I" in body)
check("marcacao: assinatura", body.endswith(f"{SIGN_OFF}\n\n~Scooby"), body[-40:])

setattr(settings, "payment_mbway", "911111111")  # noqa: B010
setattr(settings, "payment_revolut", "@example.revolut")  # noqa: B010
email.send_booking_received("ana@teste.com", "25/11/2026 17:00")
body = captured[-1][2]
check(
    "marcacao: com os dados do .env, mostra MB Way e Revolut",
    "You can send it via MB Way to 911111111 or Revolut to @example.revolut." in body,
    body,
)

# --- Confirmation ---
email.send_appointment_confirmed("ana@teste.com", "25/11/2026 17:00")
to, subject, body = captured[-1]
check("confirmacao: dia e hora", body.startswith("Your appointment has been confirmed for 25/11/2026 at 17:00."), body)
check("confirmacao: link para a ficha da cliente", f"{settings.frontend_url}/appointments" in body)
check("confirmacao: morada e assinatura", ADDRESS in body and body.endswith("~Scooby"))
email.send_deposit_confirmation("ana@teste.com", "25/11/2026 17:00")
check("sinal registado: e o email de confirmacao", captured[-1][2].startswith("Your appointment has been confirmed"))

# --- Studio bookings: booking email or confirmation ---
email.send_booked_by_studio_notification("ana@teste.com", "25/11/2026 17:00", True)
check("marcada pelo estudio, sinal por pagar: email de marcacao", captured[-1][2].startswith("Thank you for booking"))
email.send_booked_by_studio_notification("ana@teste.com", "25/11/2026 17:00", True, True)
check(
    "marcada pelo estudio com sinal pago: confirmacao",
    captured[-1][2].startswith("Your appointment has been confirmed"),
)
email.send_booked_by_studio_notification("ana@teste.com", "25/11/2026 17:00", False)
check("servico sem sinal: confirmacao", captured[-1][2].startswith("Your appointment has been confirmed"))

# --- Reminder ---
sent = email.send_attendance_reminder("ana@teste.com", datetime(2026, 11, 25, 10, 0), date(2026, 11, 24))
to, subject, body = captured[-1]
check("lembrete: devolve se foi enviado", sent is True)
check("lembrete: assunto", subject == "Your appointment is coming up! ✨", subject)
check("lembrete: amanha a hora certa", "we have an appointment tomorrow at 10:00." in body, body)
check("lembrete: morada e assinatura", ADDRESS in body and body.endswith("~Scooby"))
email.send_attendance_reminder("ana@teste.com", datetime(2026, 11, 26, 10, 0), date(2026, 11, 24))
check("lembrete: se nao for amanha, diz a data", "an appointment on 26/11/2026 at 10:00." in captured[-1][2])

# --- The address in the other email with a date ---
email.send_changed_by_studio_notification("ana@teste.com", "24/11/2026 10:00", "25/11/2026 10:00", "Removal")
check("mudada pelo estudio: tem a morada", ADDRESS in captured[-1][2])
