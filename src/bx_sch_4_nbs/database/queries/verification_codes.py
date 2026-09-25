from datetime import timedelta

from sqlmodel import Session, col, delete, select

from bx_sch_4_nbs.database.exceptions import (
    InvalidVerificationCodeError,
    VerificationCodeCooldownError,
)
from bx_sch_4_nbs.database.models import User, VerificationCode
from bx_sch_4_nbs.database.types import VerificationPurpose
from bx_sch_4_nbs.helpers.common import utc_now
from bx_sch_4_nbs.helpers.security import (
    generate_verification_code,
    hash_verification_code,
    verification_code_matches,
)

CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5


def _get_code(session: Session, user: User, purpose: VerificationPurpose) -> VerificationCode | None:
    return session.exec(
        select(VerificationCode).where(VerificationCode.user_id == user.id, VerificationCode.purpose == purpose)
    ).first()


def issue_code(session: Session, user: User, purpose: VerificationPurpose) -> str:
    if user.id is None:
        raise ValueError("User must be saved before issuing a verification code.")

    now = utc_now()

    session.exec(delete(VerificationCode).where(col(VerificationCode.expires_at) < now))
    entry = _get_code(session, user, purpose)

    if entry is not None:
        if entry.attempts >= MAX_ATTEMPTS:
            raise VerificationCodeCooldownError("Too many attempts. Try again in a few minutes.")
        if now - entry.sent_at < RESEND_COOLDOWN:
            raise VerificationCodeCooldownError("Please wait a minute before requesting a new code.")

    code = generate_verification_code()

    if entry is None:
        entry = VerificationCode(user_id=user.id, purpose=purpose, code_hash="", sent_at=now, expires_at=now)

    entry.code_hash = hash_verification_code(code)
    entry.attempts = 0
    entry.sent_at = now
    entry.expires_at = now + CODE_TTL
    session.add(entry)
    session.flush()

    return code


def verify_code(session: Session, user: User, purpose: VerificationPurpose, code: str) -> None:
    entry = _get_code(session, user, purpose)

    if entry is None or entry.expires_at < utc_now() or entry.attempts >= MAX_ATTEMPTS:
        raise InvalidVerificationCodeError("Invalid or expired code. Please request a new one.")

    if not verification_code_matches(code, entry.code_hash):
        entry.attempts += 1
        session.add(entry)
        # Must persist the failed attempt even though the request fails, otherwise
        # the rollback in get_session would reset the counter and allow brute force.
        session.commit()
        raise InvalidVerificationCodeError("Invalid or expired code. Please request a new one.")

    session.delete(entry)
