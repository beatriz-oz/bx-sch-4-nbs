from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.helpers import email

captured: list[tuple[str, str, str]] = []
setattr(email, "send_email", lambda to, subject, body: captured.append((to, subject, body)))  # noqa: B010


def check(label: str, ok: bool) -> None:
    print("OK    " if ok else "ERRO  ", label)


email.send_attendance_reminder("ana@teste.com", "15/10/2026 10:00", "abc123")
to, subject, body = captured[-1]
check("lembrete: vai para a cliente", to == "ana@teste.com")
check("lembrete: assunto e de lembrete", "reminder" in subject.lower())
check("lembrete: tem a data da marcacao", "15/10/2026 10:00" in body)
check("lembrete: tem a morada do estudio", "Rua de Passos Manuel, 228" in body and "4000-382 Porto" in body)
check("lembrete: tem o link certo", f"{settings.frontend_url}/confirm-attendance?token=abc123" in body)
check("lembrete: ja nao ameaca cancelar", "will be cancelled" not in body and "in time" not in body)
check("lembrete: lembra a regra das 48h", f"{settings.free_cancellation_hours} hours" in body)
check(
    "lembrete: deixou de haver emails de auto-cancelamento",
    not hasattr(email, "send_auto_cancelled_notification_client"),
)
