from datetime import datetime

from pydantic import BaseModel, ConfigDict

from bx_sch_4_nbs.routers.schemas.types import InstagramHandle


class PreApprovedInstagramResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instagram: str
    created_at: datetime


class NewPreApprovedInstagram(BaseModel):
    instagram: InstagramHandle
