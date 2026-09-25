from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from bx_sch_4_nbs.database.exceptions import DuplicateResourceError, ResourceDoesNotExistError
from bx_sch_4_nbs.database.models import PreApprovedInstagram


def list_pre_approved_instagrams(session: Session) -> Sequence[PreApprovedInstagram]:
    return session.exec(select(PreApprovedInstagram).order_by(PreApprovedInstagram.instagram)).all()


def create_pre_approved_instagram(session: Session, instagram: str) -> PreApprovedInstagram:
    entry = PreApprovedInstagram(instagram=instagram)
    session.add(entry)

    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateResourceError(f"@{instagram} is already pre-approved.") from error

    session.refresh(entry)
    return entry


def delete_pre_approved_instagram(session: Session, entry_id: int) -> None:
    entry = session.get(PreApprovedInstagram, entry_id)
    if entry is None:
        raise ResourceDoesNotExistError(f"Pre-approved Instagram {entry_id} does not exist.")
    session.delete(entry)
