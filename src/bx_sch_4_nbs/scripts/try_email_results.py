import logging
import smtplib
from typing import Self

from bx_sch_4_nbs.helpers import email

logging.disable(logging.CRITICAL)


def check(label: str, ok: bool) -> None:
    print("OK    " if ok else "ERRO  ", label)


class FakeSMTP:
    refuse: set[str] = set()  # noqa: RUF012

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def starttls(self) -> None:
        pass

    def login(self, *args: object) -> None:
        pass

    def send_message(self, message) -> None:
        if message["To"] in self.refuse:
            raise smtplib.SMTPRecipientsRefused({message["To"]: (550, b"mailbox full")})


class DownSMTP(FakeSMTP):
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise ConnectionRefusedError("server is down")


def reminder(to: str) -> bool:
    return email.send_attendance_reminder(to, "15/10/2026 10:00", "15/10/2026 06:00", "abc")


setattr(email.smtplib, "SMTP", FakeSMTP)  # noqa: B010
check("servidor ok: lembrete devolve True", reminder("ana@teste.com") is True)

FakeSMTP.refuse = {"cheia@teste.com"}
check("caixa cheia: lembrete devolve False", reminder("cheia@teste.com") is False)

messages = [email._build_message(to, "s", "b") for to in ["a@t.com", "cheia@teste.com", "b@t.com"]]
check(
    "varios emails: so o que falhou volta no conjunto",
    email.send_emails(messages) == {"cheia@teste.com"},
)

setattr(email.smtplib, "SMTP", DownSMTP)  # noqa: B010
try:
    result = reminder("ana@teste.com")
    check("servidor fora do ar: nao quebra e devolve False", result is False)
except Exception as error:  # noqa: BLE001
    check(f"servidor fora do ar: nao quebra ({type(error).__name__})", False)

check(
    "servidor fora do ar: todos voltam como falhos",
    email.send_emails(messages) == {"a@t.com", "cheia@teste.com", "b@t.com"},
)
