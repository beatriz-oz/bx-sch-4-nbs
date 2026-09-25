from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from bx_sch_4_nbs.database.exceptions import InvalidVerificationCodeError
from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.queries import approved_list, users, verification_codes
from bx_sch_4_nbs.database.types import VerificationPurpose
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import mask_email
from bx_sch_4_nbs.helpers.email import send_verification_code
from bx_sch_4_nbs.helpers.security import decrypt_email
from bx_sch_4_nbs.routers.schemas.auth import (
    CheckInStart,
    CheckInVerify,
    CodeSent,
    TokenResult,
)
from bx_sch_4_nbs.routers.schemas.responses import CodeSentResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


def token_response(user: User) -> TokenResponse:
    return TokenResponse(status="OK", detail=TokenResult(access_token=create_access_token(user)))


@router.post(
    "/checkin/start",
    description="Start a first-time booking with a pre-approved Instagram handle. Sends a code by email.",
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "Instagram handle not pre-approved"},
        status.HTTP_409_CONFLICT: {"description": "Account already active, or phone/email already registered"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Code requested too recently"},
    },
)
def check_in_start(session: DatabaseSession, data: CheckInStart, background_tasks: BackgroundTasks) -> CodeSentResponse:
    if not approved_list.is_pre_approved(session, data.instagram):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This Instagram handle is not pre-approved. Contact @nailsbyscooby on Instagram.",
        )

    user = users.get_user_by_instagram(session, data.instagram)
    personal_data = {
        "name": data.name,
        "last_name": data.last_name,
        "email": data.email,
        "phone": data.phone,
    }

    if user is None:
        user = users.create_first_time_user(session, instagram=data.instagram, **personal_data)
    elif user.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "This account is already active. Please log in.")
    elif user.email_verified:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You are already registered. Please activate your account by creating a password.",
        )
    else:
        users.update_unverified_user(session, user, **personal_data)

    code = verification_codes.issue_code(session, user, VerificationPurpose.CHECKIN)
    email = decrypt_email(user.email_encrypted)
    background_tasks.add_task(send_verification_code, email, code)

    return CodeSentResponse(status="OK", detail=CodeSent(sent_to=mask_email(email)))


@router.post(
    "/checkin/verify",
    description="Confirm the email code and receive an access token",
    responses={status.HTTP_400_BAD_REQUEST: {"description": "Invalid or expired code"}},
)
def check_in_verify(session: DatabaseSession, data: CheckInVerify) -> TokenResponse:
    user = users.get_user_by_instagram(session, data.instagram)
    if user is None or user.is_active or user.email_verified:
        raise InvalidVerificationCodeError("Invalid or expired code. Please request a new one.")

    verification_codes.verify_code(session, user, VerificationPurpose.CHECKIN, data.code)
    user.email_verified = True
    session.add(user)

    return token_response(user)
