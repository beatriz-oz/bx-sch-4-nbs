from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegistration(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
        json_schema_extra={"format": "password"},
    )
    instagram: str | None = Field(default=None, max_length=255)


class UserRegistrationResult(BaseModel):
    id: int
    name: str
    last_name: str
    instagram: str | None
    is_active: bool
    created_at: datetime
