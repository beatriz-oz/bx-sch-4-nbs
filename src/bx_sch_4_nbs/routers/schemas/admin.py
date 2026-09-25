from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from bx_sch_4_nbs.helpers.common import INSTAGRAM_PATTERN, normalize_instagram


class NewPreApprovedInstagram(BaseModel):
    instagram: str

    @field_validator("instagram")
    @classmethod
    def validate_instagram(cls, value: str) -> str:
        normalized = normalize_instagram(value)
        if not INSTAGRAM_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid Instagram handle")
        return normalized


class PreApprovedInstagramResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instagram: str
    created_at: datetime
