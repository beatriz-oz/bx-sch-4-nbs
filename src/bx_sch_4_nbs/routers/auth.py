from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from bx_sch_4_nbs.database.exceptions import InvalidVerificationCodeError
from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.queries import approved_list, users, verification_codes
from bx_sch_4_nbs.database.types import VerificationPurpose
from bx_sch_4_nbs.helpers.authentication import CurrentUser, create_access_token
from bx_sch_4_nbs.helpers.common import mask_email
from bx_sch_4_nbs.helpers.email import send_verification_code
from bx_sch_4_nbs.helpers.security import decrypt_email, decrypt_phone, verify_password
from bx_sch_4_nbs.routers.schemas.auth import (
    ActivationConfirm,
    ActivationStart,
    CheckInStart,
    CheckInVerify,
    CodeSent,
    Login,
    TokenResult,
    UserResult,
)
from bx_sch_4_nbs.routers.schemas.responses import (
    CodeSentResponse,
    TokenResponse,
    UserResponse,
)

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


@router.post(
    "/activation/start",
    description="Start account activation for an inactive client. Sends a code to the registered email.",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Phone not registered"},
        status.HTTP_409_CONFLICT: {"description": "Account already active"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Code requested too recently"},
    },
)
def activation_start(
    session: DatabaseSession, data: ActivationStart, background_tasks: BackgroundTasks
) -> CodeSentResponse:
    user = users.get_user_by_phone(session, data.phone)

    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Phone number not found. The first booking must be made through Instagram check-in.",
        )
    if user.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "This account is already active. Please log in.")

    code = verification_codes.issue_code(session, user, VerificationPurpose.ACTIVATION)
    email = decrypt_email(user.email_encrypted)
    background_tasks.add_task(send_verification_code, email, code)

    return CodeSentResponse(status="OK", detail=CodeSent(sent_to=mask_email(email)))


@router.post(
    "/activation/confirm",
    description="Confirm the email code and set a password to become a regular client",
    responses={status.HTTP_400_BAD_REQUEST: {"description": "Invalid or expired code"}},
)
def activation_confirm(session: DatabaseSession, data: ActivationConfirm) -> TokenResponse:
    user = users.get_user_by_phone(session, data.phone)
    if user is None or user.is_active:
        raise InvalidVerificationCodeError("Invalid or expired code. Please request a new one.")

    verification_codes.verify_code(session, user, VerificationPurpose.ACTIVATION, data.code)
    users.activate_user(session, user, data.password)

    return token_response(user)


@router.post(
    "/login",
    description="Log in with phone and password",
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Invalid phone or password"}},
)
def login(session: DatabaseSession, data: Login) -> TokenResponse:
    user = users.get_user_by_phone(session, data.phone)

    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "If it is your first time, please check in with your pre-approved Instagram handle.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Your account is not active. Please activate your account by creating a password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif user.password_hash is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        return token_response(user)


@router.get("/me", description="Data of the logged-in user")
def me(user: CurrentUser) -> UserResponse:
    if user.id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "User not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserResponse(
        status="OK",
        detail=UserResult(
            id=user.id,
            name=user.name,
            last_name=user.last_name,
            instagram=user.instagram,
            email=decrypt_email(user.email_encrypted),
            phone=decrypt_phone(user.phone_encrypted),
            role=user.role,
            is_active=user.is_active,
            email_verified=user.email_verified,
        ),
    )
