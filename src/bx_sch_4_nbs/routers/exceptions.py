from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from bx_sch_4_nbs.database.exceptions import (
    DuplicateResourceError,
    ResourceDoesNotExistError,
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


def setup_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        DuplicateResourceError,
        handle_duplicate_resource,
    )
    app.add_exception_handler(
        ResourceDoesNotExistError,
        handle_missing_resource,
    )