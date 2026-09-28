from pydantic import BaseModel, ConfigDict, Field

from bx_sch_4_nbs.routers.schemas.types import InstagramHandle, StudioDatetime


class PreApprovedInstagramResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instagram: str
    created_at: StudioDatetime


class NewPreApprovedInstagram(BaseModel):
    instagram: InstagramHandle


class NewPolicy(BaseModel):
    version: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1)


class PolicyResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: str
    content: str
    published_at: StudioDatetime
