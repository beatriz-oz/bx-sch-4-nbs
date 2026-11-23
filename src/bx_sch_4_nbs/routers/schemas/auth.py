from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from bx_sch_4_nbs.database.types import UserRole
from bx_sch_4_nbs.routers.schemas.types import InstagramHandle, Password, PhoneNumber


class CheckInStart(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    instagram: InstagramHandle
    name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: PhoneNumber


class CheckInResume(BaseModel):
    instagram: InstagramHandle


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
    email: str | None
    phone: str | None
    role: UserRole
    is_active: bool
    email_verified: bool
    wants_agenda_emails: bool
    can_create_password: bool


class ProfileUpdate(BaseModel):
    """Only what is sent changes: her name, her Instagram (clients), or the "agenda is open" emails."""

    model_config = ConfigDict(str_strip_whitespace=True)

    wants_agenda_emails: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    instagram: InstagramHandle | None = None

    @model_validator(mode="after")
    def validate_something(self) -> Self:
        if all(value is None for value in (self.wants_agenda_emails, self.name, self.last_name, self.instagram)):
            raise ValueError("Send at least one thing to change.")
        return self


class PasswordCreate(BaseModel):
    password: Password


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128, json_schema_extra={"format": "password"})
    new_password: Password


class EmailChangeStart(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    current_password: str = Field(max_length=128, json_schema_extra={"format": "password"})
    new_email: EmailStr


class EmailChangeConfirm(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class PhoneChange(BaseModel):
    current_password: str = Field(max_length=128, json_schema_extra={"format": "password"})
    new_phone: PhoneNumber


class PasswordResetStart(BaseModel):
    phone: PhoneNumber


class PasswordResetConfirm(BaseModel):
    phone: PhoneNumber
    code: str = Field(pattern=r"^\d{6}$")
    password: Password
