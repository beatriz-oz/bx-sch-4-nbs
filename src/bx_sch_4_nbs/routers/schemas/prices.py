from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from bx_sch_4_nbs.database.types import Addon, NailArtLevel, NailSize, Service
from bx_sch_4_nbs.routers.schemas.types import StudioDatetime

Amount = Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)]


class ServicePriceResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service: Service
    nail_size: NailSize | None
    amount: Decimal
    updated_at: StudioDatetime


class NailArtPriceResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nail_art_level: NailArtLevel
    amount: Decimal
    updated_at: StudioDatetime


class AddonPriceResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    addon: Addon
    amount: Decimal
    updated_at: StudioDatetime


class PriceList(BaseModel):
    services: list[ServicePriceResult]
    nail_art: list[NailArtPriceResult]
    addons: list[AddonPriceResult]


class ServicePriceUpdate(BaseModel):
    service: Service
    nail_size: NailSize | None = None
    amount: Amount


class NailArtPriceUpdate(BaseModel):
    nail_art_level: NailArtLevel
    amount: Amount


class AddonPriceUpdate(BaseModel):
    addon: Addon
    amount: Amount
