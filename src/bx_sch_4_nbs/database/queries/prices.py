from decimal import Decimal

from sqlmodel import Session, col, select

from bx_sch_4_nbs.database.exceptions import ResourceDoesNotExistError
from bx_sch_4_nbs.database.models import AddonPrice, NailArtPrice, ServicePrice
from bx_sch_4_nbs.database.types import Addon, NailArtLevel, NailSize, Service


def list_service_prices(session: Session) -> list[ServicePrice]:
    return list(session.exec(select(ServicePrice).order_by(col(ServicePrice.id))).all())


def list_nail_art_prices(session: Session) -> list[NailArtPrice]:
    return list(session.exec(select(NailArtPrice)).all())


def list_addon_prices(session: Session) -> list[AddonPrice]:
    return list(session.exec(select(AddonPrice)).all())


def update_service_price(
    session: Session, service: Service, nail_size: NailSize | None, amount: Decimal
) -> ServicePrice:
    price = session.exec(
        select(ServicePrice).where(ServicePrice.service == service, ServicePrice.nail_size == nail_size)
    ).first()
    if price is None:
        raise ResourceDoesNotExistError("There is no price for this service and nail size.")

    price.amount = amount
    session.add(price)
    session.flush()
    session.refresh(price)
    return price


def update_nail_art_price(session: Session, level: NailArtLevel, amount: Decimal) -> NailArtPrice:
    price = session.get(NailArtPrice, level)
    if price is None:
        raise ResourceDoesNotExistError("There is no price for this nail art level.")

    price.amount = amount
    session.add(price)
    session.flush()
    session.refresh(price)
    return price


def update_addon_price(session: Session, addon: Addon, amount: Decimal) -> AddonPrice:
    price = session.get(AddonPrice, addon)
    if price is None:
        raise ResourceDoesNotExistError("There is no price for this addon.")

    price.amount = amount
    session.add(price)
    session.flush()
    session.refresh(price)
    return price
