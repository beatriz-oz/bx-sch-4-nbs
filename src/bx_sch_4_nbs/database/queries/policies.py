from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from bx_sch_4_nbs.database.exceptions import DuplicateResourceError
from bx_sch_4_nbs.database.models import Policy


def get_current_policy(session: Session) -> Policy | None:
    return session.exec(select(Policy).order_by(col(Policy.id).desc())).first()


def publish_policy(session: Session, version: str, content: str) -> Policy:
    policy = Policy(version=version, content=content)
    session.add(policy)

    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateResourceError(f"Policy version {version} already exists.") from error

    session.refresh(policy)
    return policy
