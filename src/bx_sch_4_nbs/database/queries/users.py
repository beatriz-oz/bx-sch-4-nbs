from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from bx_sch_4_nbs.database.exceptions import DuplicateResourceError
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.types import UserRole
from bx_sch_4_nbs.helpers.security import encrypt_email, hash_email, hash_password
from bx_sch_4_nbs.routers.schemas.users import UserRegistration


def create_user(
    session: Session,
    new_user: UserRegistration,
) -> User:
    email_hash = hash_email(new_user.email)

    existing_user = session.exec(select(User).where(User.email_hash == email_hash)).first()

    if existing_user is not None:
        raise DuplicateResourceError("A user with this email already exists.")

    try:
        user = User(
            name=new_user.name,
            last_name=new_user.last_name,
            instagram=new_user.instagram,
            email_encrypted=encrypt_email(new_user.email),
            email_hash=email_hash,
            password_hash=hash_password(new_user.password),
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )

        session.add(user)
        session.flush()

        return user

    except IntegrityError as error:
        session.rollback()

        raise DuplicateResourceError("A user with this email already exists.") from error
