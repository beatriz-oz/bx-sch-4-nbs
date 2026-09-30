from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bx_sch_4_nbs.database.exceptions import (
    AppointmentNotActiveError,
    CancellationNotAllowedError,
    DuplicateResourceError,
    InvalidAttendanceTokenError,
    InvalidVerificationCodeError,
    ResourceDoesNotExistError,
    VerificationCodeCooldownError,
)


async def handle_duplicate_resource(
    _: Request,
    error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "status": "KO",
            "detail": str(error),
        },
    )


async def handle_missing_resource(
    _: Request,
    error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "status": "KO",
            "detail": str(error),
        },
    )


async def handle_invalid_verification_code(
    _: Request,
    error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "status": "KO",
            "detail": str(error),
        },
    )


async def handle_verification_code_cooldown(
    _: Request,
    error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "status": "KO",
            "detail": str(error),
        },
    )


async def handle_cancellation_not_allowed(
    _: Request,
    error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "status": "KO",
            "detail": str(error),
        },
    )


async def handle_invalid_attendance_token(
    _: Request,
    error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "status": "KO",
            "detail": str(error),
        },
    )


async def handle_appointment_not_active(
    _: Request,
    error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "status": "KO",
            "detail": str(error),
        },
    )


def setup_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        DuplicateResourceError,
        handle_duplicate_resource,
    )
    app.add_exception_handler(
        ResourceDoesNotExistError,
        handle_missing_resource,
    )
    app.add_exception_handler(
        InvalidVerificationCodeError,
        handle_invalid_verification_code,
    )
    app.add_exception_handler(
        VerificationCodeCooldownError,
        handle_verification_code_cooldown,
    )
    app.add_exception_handler(
        CancellationNotAllowedError,
        handle_cancellation_not_allowed,
    )
    app.add_exception_handler(
        InvalidAttendanceTokenError,
        handle_invalid_attendance_token,
    )
    app.add_exception_handler(
        AppointmentNotActiveError,
        handle_appointment_not_active,
    )
