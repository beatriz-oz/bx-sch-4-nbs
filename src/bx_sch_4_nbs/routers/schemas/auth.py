from pydantic import BaseModel, ConfigDict, EmailStr, Field

from bx_sch_4_nbs.database.types import UserRole
from bx_sch_4_nbs.routers.schemas.types import InstagramHandle, Password, PhoneNumber


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


class ActivationStart(BaseModel):
    phone: PhoneNumber


class ActivationConfirm(BaseModel):
    phone: PhoneNumber
    code: str = Field(pattern=r"^\d{6}$")
    password: Password


class Login(BaseModel):
    phone: PhoneNumber
    password: str = Field(max_length=128, json_schema_extra={"format": "password"})


class UserResult(BaseModel):
    id: int
    name: str
    last_name: str
    instagram: str | None
    email: str
    phone: str
    role: UserRole
    is_active: bool
    email_verified: bool
