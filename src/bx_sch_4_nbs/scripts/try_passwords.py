# ruff: noqa: DTZ001
"""Change password (logged in) and forgot password (code by email), for clients and the studio."""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.config import settings
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import User, VerificationCode
from bx_sch_4_nbs.database.types import UserRole, VerificationPurpose
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_password, hash_phone
from bx_sch_4_nbs.main import app
from bx_sch_4_nbs.routers import auth as auth_router

connection = engine.connect()
transaction = connection.begin()
session = Session(bind=connection, join_transaction_mode="create_savepoint")


def override_session():
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise


app.dependency_overrides[get_session] = override_session
client = TestClient(app, raise_server_exceptions=False)

# The emails are caught here instead of being sent: the test reads the code from them.
sent_codes: dict[str, str] = {}
changed_notices: list[str] = []


def catch_reset_code(to: str, code: str) -> None:
    sent_codes[to] = code


def catch_changed_notice(to: str) -> None:
    changed_notices.append(to)


setattr(auth_router, "send_password_reset_code", catch_reset_code)  # noqa: B010
setattr(auth_router, "send_password_changed", catch_changed_notice)  # noqa: B010


def check(label: str, ok: bool, detail: object = "") -> None:
    print("OK    " if ok else "ERRO  ", label, detail if not ok else "")


def make_user(name: str, email: str, phone: str, *, password: str | None, role: UserRole = UserRole.USER) -> User:
    user = User(
        name=name,
        last_name="Password",
        instagram=None if role == UserRole.SUPER_ADMIN else f"{name.lower()}.password",
        email_encrypted=encrypt_email(email),
        email_hash=hash_email(email),
        phone_encrypted=encrypt_phone(phone),
        phone_hash=hash_phone(phone),
        password_hash=hash_password(password) if password else None,
        role=role,
        is_active=password is not None,
        email_verified=True,
        approved_at=datetime(2026, 1, 1),
    )
    session.add(user)
    return user


def old_token(user: User) -> dict[str, str]:
    """A login token from 10 seconds ago: the session of another device, opened before the change."""
    issued = datetime.now(tz=UTC) - timedelta(seconds=10)
    payload = {"sub": str(user.id), "iat": issued, "exp": issued + timedelta(hours=1), "purpose": "access"}
    return {"Authorization": f"Bearer {jwt.encode(payload, settings.jwt_secret_key, settings.jwt_algorithm)}"}


def bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['detail']['access_token']}"}


def login(phone: str, password: str):
    return client.post("/v1/auth/login", json={"phone": phone, "password": password})


DORA_PHONE, DORA_EMAIL = "+351915222001", "dora@password.test"
ADMIN_PHONE, ADMIN_EMAIL = "+351915222002", "studio@password.test"
NEW_PHONE = "+351915222003"
dora = make_user("Dora", DORA_EMAIL, DORA_PHONE, password="old-password-1")
studio = make_user("Studio", ADMIN_EMAIL, ADMIN_PHONE, password="studio-pass-1", role=UserRole.SUPER_ADMIN)
newbie = make_user("Nina", "nina@password.test", NEW_PHONE, password=None)
session.commit()

# --- Change password (logged in) ---
other_device = old_token(dora)
r = login(DORA_PHONE, "old-password-1")
dora_auth = bearer(r)
check("other device works before the change", client.get("/v1/auth/me", headers=other_device).status_code == 200)

r = client.post(
    "/v1/auth/me/password", headers=dora_auth, json={"current_password": "wrong", "new_password": "new-password-1"}
)
check("wrong current password -> 400 (not 401: she stays logged in)", r.status_code == 400, r.status_code)
r = client.post(
    "/v1/auth/me/password", headers=dora_auth, json={"current_password": "old-password-1", "new_password": "short"}
)
check("new password under 8 characters -> 422", r.status_code == 422, r.status_code)
r = client.post(
    "/v1/auth/me/password",
    headers=dora_auth,
    json={"current_password": "old-password-1", "new_password": "old-password-1"},
)
check("same as the current one -> 400", r.status_code == 400, r.text)
r = client.post("/v1/auth/me/password", json={"current_password": "old-password-1", "new_password": "new-password-1"})
check("not logged in -> 401", r.status_code == 401, r.status_code)

r = client.post(
    "/v1/auth/me/password",
    headers=dora_auth,
    json={"current_password": "old-password-1", "new_password": "new-password-1"},
)
check("change -> 200 with a new token", r.status_code == 200 and "access_token" in r.text, r.text)
new_auth = bearer(r)
check("the new token works", client.get("/v1/auth/me", headers=new_auth).status_code == 200)
check("the other device is logged out", client.get("/v1/auth/me", headers=other_device).status_code == 401)
check("a notice email went to her", changed_notices == [DORA_EMAIL], changed_notices)
check("old password no longer logs in", login(DORA_PHONE, "old-password-1").status_code == 401)
check("new password logs in", login(DORA_PHONE, "new-password-1").status_code == 200)

r = client.post(
    "/v1/auth/me/password",
    headers={"Authorization": f"Bearer {create_access_token(newbie)}"},
    json={"current_password": "anything", "new_password": "new-password-1"},
)
check("a client without a password yet -> 409", r.status_code == 409, r.status_code)

# The studio too.
r = login(ADMIN_PHONE, "studio-pass-1")
r = client.post(
    "/v1/auth/me/password",
    headers=bearer(r),
    json={"current_password": "studio-pass-1", "new_password": "studio-pass-2"},
)
check("the studio changes hers -> 200", r.status_code == 200, r.text)
check("the studio logs in with the new one", login(ADMIN_PHONE, "studio-pass-2").status_code == 200)

# --- Forgot password ---
changed_notices.clear()
generic = "If this phone belongs to an account with a password"
r = client.post("/v1/auth/password/forgot", json={"phone": DORA_PHONE})
check("forgot -> 200", r.status_code == 200 and generic in r.text, r.text)
check("a code went to her email", DORA_EMAIL in sent_codes, sent_codes)
r_unknown = client.post("/v1/auth/password/forgot", json={"phone": "+351915222999"})
r_newbie = client.post("/v1/auth/password/forgot", json={"phone": NEW_PHONE})
check(
    "unknown phone and no-password client get the SAME answer",
    r_unknown.status_code == 200 and r_newbie.status_code == 200 and r_unknown.json() == r.json() == r_newbie.json(),
    (r_unknown.text, r_newbie.text),
)
check("...and no email for them", len(sent_codes) == 1, sent_codes)
r = client.post("/v1/auth/password/forgot", json={"phone": DORA_PHONE})
check("asking again at once -> 429", r.status_code == 429, r.status_code)
r = client.post("/v1/auth/password/forgot", json={"phone": "12"})
check("invalid phone -> 422", r.status_code == 422, r.status_code)

code = sent_codes[DORA_EMAIL]
wrong = "000000" if code != "000000" else "111111"
other_device = old_token(dora)
r = client.post("/v1/auth/password/reset", json={"phone": DORA_PHONE, "code": wrong, "password": "reset-password-1"})
check("wrong code -> 400", r.status_code == 400, r.status_code)
r = client.post("/v1/auth/password/reset", json={"phone": NEW_PHONE, "code": code, "password": "reset-password-1"})
check("a no-password client cannot use it -> 400", r.status_code == 400, r.status_code)
r = client.post("/v1/auth/password/reset", json={"phone": DORA_PHONE, "code": code, "password": "reset-password-1"})
check("right code -> 200 with a token (logged in)", r.status_code == 200 and "access_token" in r.text, r.text)
check("that token works", client.get("/v1/auth/me", headers=bearer(r)).status_code == 200)
check("the other device is logged out", client.get("/v1/auth/me", headers=other_device).status_code == 401)
check("a notice email went to her", changed_notices == [DORA_EMAIL], changed_notices)
check("the new password logs in", login(DORA_PHONE, "reset-password-1").status_code == 200)
r = client.post("/v1/auth/password/reset", json={"phone": DORA_PHONE, "code": code, "password": "another-pass-1"})
check("the same code cannot be used twice -> 400", r.status_code == 400, r.status_code)
left = session.exec(select(VerificationCode).where(VerificationCode.user_id == dora.id)).all()
check("no code left waiting", len(left) == 0, left)

# Brute force: 5 wrong codes and even the right one stops working.
sent_codes.clear()
for entry in session.exec(select(VerificationCode).where(VerificationCode.user_id == studio.id)).all():
    session.delete(entry)
session.commit()
client.post("/v1/auth/password/forgot", json={"phone": ADMIN_PHONE})
studio_code = sent_codes.get(ADMIN_EMAIL, "")
check("the studio can ask for a code too", studio_code != "", sent_codes)
bad = "000000" if studio_code != "000000" else "111111"
for _ in range(5):
    client.post("/v1/auth/password/reset", json={"phone": ADMIN_PHONE, "code": bad, "password": "studio-pass-3"})
r = client.post(
    "/v1/auth/password/reset", json={"phone": ADMIN_PHONE, "code": studio_code, "password": "studio-pass-3"}
)
check("after 5 wrong tries, the right code is refused too", r.status_code == 400, r.status_code)
entry = session.exec(
    select(VerificationCode).where(
        VerificationCode.user_id == studio.id, VerificationCode.purpose == VerificationPurpose.PASSWORD_RESET
    )
).first()
check("the failed tries were counted", entry is not None and entry.attempts == 5, entry)

session.close()
transaction.rollback()
connection.close()
