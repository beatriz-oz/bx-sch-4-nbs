from typing import Literal, TypeVar

from pydantic import BaseModel

from bx_sch_4_nbs.routers.schemas import admin, auth

T = TypeVar("T")


class Page[T](BaseModel):
    items: list[T]
    page_number: int
    page_content_size: int
    total: int
    size: int


class BaseResponse[T](BaseModel):
    status: Literal["OK", "KO"]
    detail: T


MessageResponse = BaseResponse[str]
PreApprovedInstagramResponse = BaseResponse[admin.PreApprovedInstagramResult]
PreApprovedInstagramListResponse = BaseResponse[list[admin.PreApprovedInstagramResult]]
CodeSentResponse = BaseResponse[auth.CodeSent]
TokenResponse = BaseResponse[auth.TokenResult]
