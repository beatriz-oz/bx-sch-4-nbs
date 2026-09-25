from pydantic import BaseModel, ConfigDict, EmailStr, Field

from bx_sch_4_nbs.routers.schemas.types import InstagramHandle, PhoneNumber


class CheckInStart(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    instagram: InstagramHandle
    name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: PhoneNumber


class CheckInVerify(BaseModel):
    instagram: InstagramHandle
    code: str = Field(pattern=r"^\d{6}$")


class CodeSent(BaseModel):
    sent_to: str


class TokenResult(BaseModel):
    access_token: str
    token_type: str = "bearer"
