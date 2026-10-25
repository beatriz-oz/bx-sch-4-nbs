from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.exceptions import (
    InvalidAttendanceTokenError,
)
from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.types import UserRole

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "purpose": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DatabaseSession,
) -> User:
    if credentials is None:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(payload["sub"])

        if payload["purpose"] != "access":
            raise InvalidTokenError

    except (InvalidTokenError, KeyError, ValueError) as error:
        raise CREDENTIALS_EXCEPTION from error

    user = session.get(User, user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION

    return user


def create_attendance_token(appointment_id: int, expires_at: datetime) -> str:

    payload = {
        "sub": str(appointment_id),
        "exp": expires_at.replace(tzinfo=UTC),
        "purpose": "attendance",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def read_attendance_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload["purpose"] != "attendance":
            raise InvalidAttendanceTokenError("This link is not an attendance confirmation link.")
        return int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError) as error:
        raise InvalidAttendanceTokenError("This confirmation link is invalid or has expired.") from error


def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


type CurrentUser = Annotated[User, Depends(get_current_user)]
type CurrentAdmin = Annotated[User, Depends(get_current_admin)]
