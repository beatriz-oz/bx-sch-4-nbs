"""
The minimum an empty database needs before the tests: a super admin and a published policy.
(The prices come with the migrations; the demo clients and appointments come from seed_demo.)

    uv run python -m bx_sch_4_nbs.scripts.seed_ci

Made for CI (Jenkins), where nobody can answer create_admin's questions. Safe to run twice:
whatever already exists is kept. Never use these values in production.
"""

from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import Policy, User
from bx_sch_4_nbs.database.types import UserRole
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_password, hash_phone

CI_ADMIN_EMAIL = "admin@ci.test"
CI_ADMIN_PHONE = "+351910000000"


def main() -> None:
    with Session(engine) as session:
        if session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first() is None:
            session.add(
                User(
                    name="CI",
                    last_name="Admin",
                    email_encrypted=encrypt_email(CI_ADMIN_EMAIL),
                    email_hash=hash_email(CI_ADMIN_EMAIL),
                    phone_encrypted=encrypt_phone(CI_ADMIN_PHONE),
                    phone_hash=hash_phone(CI_ADMIN_PHONE),
                    password_hash=hash_password("ci-admin-password"),
                    role=UserRole.SUPER_ADMIN,
                    is_active=True,
                    email_verified=True,
                )
            )
            print("Created the CI admin.")

        if session.exec(select(Policy)).first() is None:
            session.add(Policy(version="ci-1", content="Booking policies used by the automated tests."))
            print("Published the CI policy.")

        session.commit()


if __name__ == "__main__":
    main()
