from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from bx_sch_4_nbs.database.exceptions import DuplicateResourceError
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.helpers.security import (
    encrypt_email,
    encrypt_phone,
    hash_email,
    hash_phone,
)

DUPLICATE_MESSAGES = {
    "uc_users_phone_hash": "This phone number is already registered.",
    "uc_users_email_hash": "This email is already registered.",
    "uc_users_instagram": "This Instagram handle is already registered.",
}


def _flush_or_raise_duplicate(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as error:
        message = next(
            (msg for constraint, msg in DUPLICATE_MESSAGES.items() if constraint in str(error.orig)),
            "User already exists.",
        )
        raise DuplicateResourceError(message) from error


def get_user_by_instagram(session: Session, instagram: str) -> User | None:
    return session.exec(select(User).where(User.instagram == instagram)).first()


def create_first_time_user(
    session: Session,
    *,
    instagram: str,
    name: str,
    last_name: str,
    email: str,
    phone: str,
) -> User:
    user = User(
        instagram=instagram,
        name=name,
        last_name=last_name,
        email_encrypted="",
        email_hash="",
        phone_encrypted="",
        phone_hash="",
    )
    session.add(user)
    update_unverified_user(session, user, name=name, last_name=last_name, email=email, phone=phone)
    return user


def update_unverified_user(session: Session, user: User, *, name: str, last_name: str, email: str, phone: str) -> None:
    user.name = name
    user.last_name = last_name
    user.email_encrypted = encrypt_email(email)
    user.email_hash = hash_email(email)
    user.phone_encrypted = encrypt_phone(phone)
    user.phone_hash = hash_phone(phone)
    session.add(user)
    _flush_or_raise_duplicate(session)
