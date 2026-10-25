from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.helpers import email

captured: list[tuple[str, str, str]] = []
setattr(email, "send_email", lambda to, subject, body: captured.append((to, subject, body)))  # noqa: B010


def check(label: str, ok: bool) -> None:
    print("OK    " if ok else "ERRO  ", label)


email.send_attendance_reminder("ana@teste.com", "15/10/2026 10:00", "15/10/2026 06:00", "abc123")
to, subject, body = captured[-1]
check("lembrete: vai para a cliente", to == "ana@teste.com")
check("lembrete: assunto pede confirmacao", "confirm" in subject.lower())
check("lembrete: tem a data da marcacao", "15/10/2026 10:00" in body)
check("lembrete: tem o prazo", "15/10/2026 06:00" in body)
check("lembrete: tem o link certo", f"{settings.frontend_url}/confirm-attendance?token=abc123" in body)
check("lembrete: avisa do sinal", "deposit" in body.lower())

email.send_auto_cancelled_notification_client("ana@teste.com", "15/10/2026 10:00")
to, subject, body = captured[-1]
check("cliente: assunto de cancelamento", "cancelled" in subject.lower())
check("cliente: tem a data", "15/10/2026 10:00" in body)
check("cliente: fala do sinal", "deposit" in body.lower())

email.send_auto_cancelled_notification_studio("studio@x", "ana.nails", "Ana Silva", "15/10/2026 10:00", True, True)
to, subject, body = captured[-1]
check("salao: assunto comeca com CANCELLED", subject.startswith("CANCELLED"))
check("salao: tem o @ da cliente", "@ana.nails" in body)
check("salao: tem o nome", "Ana Silva" in body)
check("salao, sinal pago: diz que nao e devolvido", "not refunded" in body)
check("salao, cliente avisada: sem ACTION REQUIRED", "ACTION REQUIRED" not in subject)
check("salao, cliente avisada: comeca direto no aviso, sem linhas vazias", body.startswith("Appointment"))

email.send_auto_cancelled_notification_studio("studio@x", None, "Ana Silva", "15/10/2026 10:00", False, True)
to, subject, body = captured[-1]
check("salao, sem Instagram: mostra 'no Instagram'", "no Instagram" in body)
check("salao, sinal nao pago: diz que nao foi pago", "had not been paid" in body)

email.send_auto_cancelled_notification_studio("studio@x", "ana.nails", "Ana Silva", "15/10/2026 10:00", True, False)
to, subject, body = captured[-1]
check("salao, cliente NAO avisada: assunto com ACTION REQUIRED", "ACTION REQUIRED" in subject)
check("salao, cliente NAO avisada: pede para contatar a cliente", "contact the client" in body)
