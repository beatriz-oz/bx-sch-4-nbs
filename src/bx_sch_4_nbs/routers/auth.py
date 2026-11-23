from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from bx_sch_4_nbs.database.exceptions import InvalidVerificationCodeError
from bx_sch_4_nbs.database.helpers import DatabaseSession
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.queries import approved_list, users, verification_codes
from bx_sch_4_nbs.database.types import UserRole, VerificationPurpose
from bx_sch_4_nbs.helpers.authentication import CurrentUser, create_access_token
from bx_sch_4_nbs.helpers.common import mask_email, mask_phone
from bx_sch_4_nbs.helpers.email import (
    send_email_change_code,
    send_email_changed,
    send_password_changed,
    send_password_reset_code,
    send_phone_changed,
    send_verification_code,
)
from bx_sch_4_nbs.helpers.security import (
    decrypt_email,
    email_or_none,
    encrypt_email,
    hash_email,
    hash_phone,
    normalize_email,
    phone_or_none,
    required_email,
    verify_password,
)
from bx_sch_4_nbs.routers.schemas.auth import (
    ActivationConfirm,
    ActivationStart,
    CheckInResume,
    CheckInStart,
    CheckInVerify,
    CodeSent,
    EmailChangeConfirm,
    EmailChangeStart,
    Login,
    PasswordChange,
    PasswordCreate,
    PasswordResetConfirm,
    PasswordResetStart,
    PhoneChange,
    ProfileUpdate,
    TokenResult,
    UserResult,
)
from bx_sch_4_nbs.routers.schemas.responses import (
    CodeSentResponse,
    MessageResponse,
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
    email = required_email(user.email_encrypted)
    background_tasks.add_task(send_verification_code, email, code)

    return CodeSentResponse(status="OK", detail=CodeSent(sent_to=mask_email(email)))


@router.post(
    "/checkin/verify",
    description="Confirm the email code and receive an access token",
    responses={status.HTTP_400_BAD_REQUEST: {"description": "Invalid or expired code"}},
)
def check_in_verify(session: DatabaseSession, data: CheckInVerify) -> TokenResponse:
    user = users.get_user_by_instagram(session, data.instagram)
    # A first check-in (email not confirmed yet), or an approved client continuing her activation.
    if user is None or user.is_active or (user.email_verified and not can_resume_activation(user)):
        raise InvalidVerificationCodeError("Invalid or expired code. Please request a new one.")

    verification_codes.verify_code(session, user, VerificationPurpose.CHECKIN, data.code)
    user.email_verified = True
    session.add(user)

    return token_response(user)


def can_resume_activation(user: User) -> bool:
    """An approved client who checked in but has no password yet (e.g. she closed the window)."""
    return not user.is_active and user.email_verified and user.approved_at is not None and bool(user.email_encrypted)


# The same answer for an unknown handle and for any account with nothing to continue.
NOTHING_TO_RESUME = (
    "There is no activation to continue for this Instagram. Fill in the form for your first appointment."
)


@router.post(
    "/checkin/resume",
    description=(
        "Continue the activation of an approved client who already checked in but did not create her password: "
        "a new code goes to the email she gave. Then /checkin/verify and /me/activate, as after a first check-in."
    ),
    responses={
        status.HTTP_409_CONFLICT: {"description": "Nothing to continue for this handle"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Code requested too recently"},
    },
)
def check_in_resume(
    session: DatabaseSession, data: CheckInResume, background_tasks: BackgroundTasks
) -> CodeSentResponse:
    user = users.get_user_by_instagram(session, data.instagram)
    if user is None or not can_resume_activation(user):
        raise HTTPException(status.HTTP_409_CONFLICT, NOTHING_TO_RESUME)

    code = verification_codes.issue_code(session, user, VerificationPurpose.CHECKIN)
    email = required_email(user.email_encrypted)
    background_tasks.add_task(send_verification_code, email, code)

    return CodeSentResponse(status="OK", detail=CodeSent(sent_to=mask_email(email)))


@router.post(
    "/activation/start",
    description="Start account activation for an inactive client. Sends a code to the registered email.",
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "The studio has not approved this client yet"},
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
    if user.approved_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Creating a password needs the studio's approval. Contact @nailsbyscooby on Instagram.",
        )

    code = verification_codes.issue_code(session, user, VerificationPurpose.ACTIVATION)
    email = required_email(user.email_encrypted)
    background_tasks.add_task(send_verification_code, email, code)

    return CodeSentResponse(status="OK", detail=CodeSent(sent_to=mask_email(email)))


@router.post(
    "/activation/confirm",
    description="Confirm the email code and set a password to become a regular client",
    responses={status.HTTP_400_BAD_REQUEST: {"description": "Invalid or expired code"}},
)
def activation_confirm(session: DatabaseSession, data: ActivationConfirm) -> TokenResponse:
    user = users.get_user_by_phone(session, data.phone)
    # The approval is checked again here: a code asked before a revoke must not work.
    if user is None or user.is_active or user.approved_at is None:
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


# The same answer whether the phone exists or not, so this form cannot be used to find out who is a client.
RESET_CODE_SENT = "If this phone belongs to an account with a password, we sent a code to its email."


@router.post(
    "/password/forgot",
    description="Forgot the password: sends a code to the account's email (clients and the studio)",
    responses={status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Code requested too recently"}},
)
def password_reset_start(
    session: DatabaseSession, data: PasswordResetStart, background_tasks: BackgroundTasks
) -> MessageResponse:
    user = users.get_user_by_phone(session, data.phone)

    # Without a password there is nothing to reset: that client creates one in the activation instead.
    if user is not None and user.is_active:
        code = verification_codes.issue_code(session, user, VerificationPurpose.PASSWORD_RESET)
        background_tasks.add_task(send_password_reset_code, required_email(user.email_encrypted), code)

    return MessageResponse(status="OK", detail=RESET_CODE_SENT)


@router.post(
    "/password/reset",
    description="Confirm the email code and choose a new password. Logs out every other device.",
    responses={status.HTTP_400_BAD_REQUEST: {"description": "Invalid or expired code"}},
)
def password_reset_confirm(
    session: DatabaseSession, data: PasswordResetConfirm, background_tasks: BackgroundTasks
) -> TokenResponse:
    user = users.get_user_by_phone(session, data.phone)
    if user is None or not user.is_active:
        raise InvalidVerificationCodeError("Invalid or expired code. Please request a new one.")

    verification_codes.verify_code(session, user, VerificationPurpose.PASSWORD_RESET, data.code)
    users.set_password(session, user, data.password)
    background_tasks.add_task(send_password_changed, required_email(user.email_encrypted))

    return token_response(user)


def user_result(user: User) -> UserResult:
    if user.id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "User not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserResult(
        id=user.id,
        name=user.name,
        last_name=user.last_name,
        instagram=user.instagram,
        email=email_or_none(user.email_encrypted),
        phone=phone_or_none(user.phone_encrypted),
        role=user.role,
        is_active=user.is_active,
        email_verified=user.email_verified,
        wants_agenda_emails=user.wants_agenda_emails,
        can_create_password=not user.is_active and user.approved_at is not None,
    )


@router.get("/me", description="Data of the logged-in user")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse(status="OK", detail=user_result(user))


@router.post(
    "/me/activate",
    description=(
        "An approved client who has just checked in creates her password at once: the check-in code "
        "already proved her email. Logs out other devices; the answer has a new token."
    ),
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "Not approved by the studio, or email not confirmed"},
        status.HTTP_409_CONFLICT: {"description": "Account already active"},
    },
)
def activate_me(session: DatabaseSession, user: CurrentUser, data: PasswordCreate) -> TokenResponse:
    if user.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "This account is already active.")
    if user.approved_at is None or not user.email_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Creating a password needs the studio's approval. Contact @nailsbyscooby on Instagram.",
        )

    users.activate_user(session, user, data.password)
    return token_response(user)


def check_current_password(user: User, current_password: str) -> None:
    """Changing the password, email or phone asks for the current password first."""
    if not user.is_active or user.password_hash is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You do not have a password yet. Create one first.")
    # 400, not 401: a 401 means "not logged in" and would log her out in the site.
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The current password is not correct.")


@router.post(
    "/me/password",
    description="Change your password (clients and the studio). Logs out every other device; "
    "the answer has a new token for this one.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Current password wrong, or the new one is the same"},
        status.HTTP_409_CONFLICT: {"description": "No password yet (create it in the activation)"},
    },
)
def change_password(
    session: DatabaseSession, user: CurrentUser, data: PasswordChange, background_tasks: BackgroundTasks
) -> TokenResponse:
    check_current_password(user, data.current_password)
    if data.new_password == data.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The new password must be different from the current one.")

    users.set_password(session, user, data.new_password)
    background_tasks.add_task(send_password_changed, required_email(user.email_encrypted))

    return token_response(user)


@router.post(
    "/me/email",
    description="Change your email, step 1: sends a code to the NEW email. Nothing changes until it is confirmed.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Current password wrong, or the email is the same"},
        status.HTTP_409_CONFLICT: {"description": "Email used by another account, or no password yet"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Code requested too recently"},
    },
)
def email_change_start(
    session: DatabaseSession, user: CurrentUser, data: EmailChangeStart, background_tasks: BackgroundTasks
) -> CodeSentResponse:
    check_current_password(user, data.current_password)
    new_email = normalize_email(data.new_email)
    if hash_email(new_email) == user.email_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is already your email.")
    if users.is_email_taken(session, new_email, by_other_than=user):
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already registered.")

    code = verification_codes.issue_code(session, user, VerificationPurpose.EMAIL_CHANGE, encrypt_email(new_email))
    background_tasks.add_task(send_email_change_code, new_email, code)

    return CodeSentResponse(status="OK", detail=CodeSent(sent_to=mask_email(new_email)))


@router.post(
    "/me/email/confirm",
    description="Change your email, step 2: the code sent to the new email. The old email gets a notice.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid or expired code"},
        status.HTTP_409_CONFLICT: {"description": "Email registered by another account in the meantime"},
    },
)
def email_change_confirm(
    session: DatabaseSession, user: CurrentUser, data: EmailChangeConfirm, background_tasks: BackgroundTasks
) -> UserResponse:
    pending = verification_codes.verify_code(session, user, VerificationPurpose.EMAIL_CHANGE, data.code)
    if pending is None:
        raise InvalidVerificationCodeError("Invalid or expired code. Please request a new one.")

    old_email = required_email(user.email_encrypted)
    new_email = decrypt_email(pending)
    users.set_email(session, user, new_email)
    background_tasks.add_task(send_email_changed, old_email, mask_email(new_email))

    return UserResponse(status="OK", detail=user_result(user))


@router.post(
    "/me/phone",
    description="Change your phone number (the one you log in with). A notice goes to your email.",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Current password wrong, or the phone is the same"},
        status.HTTP_409_CONFLICT: {"description": "Phone used by another account, or no password yet"},
    },
)
def change_phone(
    session: DatabaseSession, user: CurrentUser, data: PhoneChange, background_tasks: BackgroundTasks
) -> UserResponse:
    check_current_password(user, data.current_password)
    if hash_phone(data.new_phone) == user.phone_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is already your phone number.")

    users.set_phone(session, user, data.new_phone)
    background_tasks.add_task(send_phone_changed, required_email(user.email_encrypted), mask_phone(data.new_phone))

    return UserResponse(status="OK", detail=user_result(user))


@router.patch(
    "/me",
    description="Update your name or your preferences (e.g. stop the 'agenda is open' emails). Clients and the studio",
)
def update_me(session: DatabaseSession, user: CurrentUser, data: ProfileUpdate) -> UserResponse:
    if data.instagram is not None:
        # The studio's own account has no Instagram here: clients only.
        if user.role != UserRole.USER:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only clients have an Instagram in their profile.")
        users.set_instagram(session, user, data.instagram)
    if data.name is not None or data.last_name is not None:
        users.set_name(session, user, data.name, data.last_name)
    if data.wants_agenda_emails is not None:
        users.set_agenda_emails(session, user, data.wants_agenda_emails)
    return UserResponse(status="OK", detail=user_result(user))
