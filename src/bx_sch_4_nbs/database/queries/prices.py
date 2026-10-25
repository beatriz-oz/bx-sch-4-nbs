from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, col, func, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.exceptions import ResourceDoesNotExistError
from bx_sch_4_nbs.database.models import AddonPrice, Appointment, NailArtPrice, ServicePrice
from bx_sch_4_nbs.database.types import Addon, AppointmentStatus, NailArtLevel, NailSize, Service


@dataclass
class PossibleExtra:
    description: str
    amount: Decimal
    per_unit: bool = False


@dataclass
class Estimate:
    service: Service
    estimated_price: Decimal
    possible_extras: list[PossibleExtra] = field(default_factory=list)
    note: str | None = None


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


def _service_price(session: Session, service: Service, nail_size: NailSize | None) -> Decimal:
    price = session.exec(
        select(ServicePrice).where(ServicePrice.service == service, ServicePrice.nail_size == nail_size)
    ).first()
    if price is None:
        raise ResourceDoesNotExistError("There is no price for this service and nail size.")
    return price.amount


def _nail_art_price(session: Session, level: NailArtLevel) -> Decimal:
    price = session.get(NailArtPrice, level)
    if price is None:
        raise ResourceDoesNotExistError("There is no price for this nail art level.")
    return price.amount


def _addon_price(session: Session, addon: Addon) -> Decimal:
    price = session.get(AddonPrice, addon)
    if price is None:
        raise ResourceDoesNotExistError("There is no price for this addon.")
    return price.amount


def calculate_price(
    session: Session,
    *,
    service: Service,
    nail_size: NailSize | None,
    nail_art_level: NailArtLevel | None,
    broken_nails: int = 0,
    extra_charms: int = 0,
    complete_removal: bool = False,
) -> Decimal:
    if service == Service.OTHER:
        # The studio sets the price of OTHER; callers must handle it before calling this.
        raise ValueError("There is no price table for this service.")

    if service == Service.REMOVAL:
        return _service_price(session, service, None)

    if nail_size is None or nail_art_level is None:
        raise ValueError("Nail size and nail art level are required for this service.")

    total = (
        _service_price(session, service, nail_size)
        + _nail_art_price(session, nail_art_level)
        + _addon_price(session, Addon.BROKEN_NAIL) * broken_nails
        + _addon_price(session, Addon.EXTRA_CHARM) * extra_charms
    )
    if complete_removal:
        total += _service_price(session, Service.REMOVAL, None)

    return total


def last_completed_appointment_at(session: Session, user_id: int) -> datetime | None:
    return session.exec(
        select(func.max(Appointment.scheduled_at)).where(
            Appointment.user_id == user_id, Appointment.status == AppointmentStatus.COMPLETED
        )
    ).one()


def resolve_service(
    session: Session, user_id: int, service: Service, scheduled_at: datetime
) -> tuple[Service, str | None]:
    if service != Service.MAINTENANCE:
        return service, None

    last = last_completed_appointment_at(session, user_id)
    if last is None:
        return service, None

    if scheduled_at - last > timedelta(days=settings.maintenance_max_days):
        note = (
            f"Priced as application: the last appointment was more than "
            f"{settings.maintenance_max_days} days before this date."
        )
        return Service.APPLICATION, note

    return service, None


def estimate_price(
    session: Session,
    *,
    user_id: int,
    scheduled_at: datetime,
    service: Service,
    nail_size: NailSize | None,
    nail_art_level: NailArtLevel | None,
    broken_nails: int,
    has_other_professional_nails: bool,
) -> Estimate:
    effective_service, note = resolve_service(session, user_id, service, scheduled_at)
    return _estimate(
        session,
        service=effective_service,
        nail_size=nail_size,
        nail_art_level=nail_art_level,
        broken_nails=broken_nails,
        has_other_professional_nails=has_other_professional_nails,
        note=note,
    )


def simulate_price(
    session: Session,
    *,
    service: Service,
    nail_size: NailSize | None,
    nail_art_level: NailArtLevel | None,
    broken_nails: int,
    has_other_professional_nails: bool,
) -> Estimate:
    """
    The estimate for someone not logged in. Without knowing the client, the maintenance
    price is shown as asked, with a note on when it becomes an application.
    """
    note = None
    if service == Service.MAINTENANCE:
        note = (
            f"Maintenance price applies when the last appointment was at most "
            f"{settings.maintenance_max_days} days before. After that, it is priced as an application."
        )
    return _estimate(
        session,
        service=service,
        nail_size=nail_size,
        nail_art_level=nail_art_level,
        broken_nails=broken_nails,
        has_other_professional_nails=has_other_professional_nails,
        note=note,
    )


def _estimate(
    session: Session,
    *,
    service: Service,
    nail_size: NailSize | None,
    nail_art_level: NailArtLevel | None,
    broken_nails: int,
    has_other_professional_nails: bool,
    note: str | None,
) -> Estimate:
    total = calculate_price(
        session,
        service=service,
        nail_size=nail_size,
        nail_art_level=nail_art_level,
        broken_nails=broken_nails,
    )

    if service == Service.REMOVAL:
        return Estimate(service=service, estimated_price=total)

    extras = []
    if has_other_professional_nails:
        extras.append(
            PossibleExtra(
                description="Complete removal (nails from another professional)",
                amount=_service_price(session, Service.REMOVAL, None),
            )
        )
    extras.append(
        PossibleExtra(description="Extra charm", amount=_addon_price(session, Addon.EXTRA_CHARM), per_unit=True)
    )

    return Estimate(service=service, estimated_price=total, possible_extras=extras, note=note)
