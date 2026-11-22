# ruff: noqa: DTZ001
"""Change the email (code to the new email) and the phone (logged in, with the current password)."""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.types import UserRole
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

# The emails are caught here instead of being sent.
codes: dict[str, str] = {}
email_notices: list[tuple[str, str]] = []
phone_notices: list[tuple[str, str]] = []


def catch_code(to: str, code: str) -> None:
    codes[to] = code


def catch_email_notice(to: str, new_email_masked: str) -> None:
    email_notices.append((to, new_email_masked))


def catch_phone_notice(to: str, new_phone_masked: str) -> None:
    phone_notices.append((to, new_phone_masked))


setattr(auth_router, "send_email_change_code", catch_code)  # noqa: B010
setattr(auth_router, "send_email_changed", catch_email_notice)  # noqa: B010
setattr(auth_router, "send_phone_changed", catch_phone_notice)  # noqa: B010
setattr(auth_router, "send_password_reset_code", catch_code)  # noqa: B010


def check(label: str, ok: bool, detail: object = "") -> None:
    print("OK    " if ok else "ERRO  ", label, detail if not ok else "")


def make_user(name: str, email: str, phone: str, *, password: str | None, role: UserRole = UserRole.USER) -> User:
    user = User(
        name=name,
        last_name="Contact",
        instagram=None if role == UserRole.SUPER_ADMIN else f"{name.lower()}.contact",
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


def auth_for(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


EVA_EMAIL, EVA_PHONE = "eva@contact-test.pt", "+351916333001"
NEW_EMAIL = "eva.new@contact-test.pt"
TAKEN_EMAIL, TAKEN_PHONE = "rita@contact-test.pt", "+351916333002"
NEW_PHONE = "+351916333003"
eva = make_user("Eva", EVA_EMAIL, EVA_PHONE, password="eva-password-1")
rita = make_user("Rita", TAKEN_EMAIL, TAKEN_PHONE, password="rita-password-1")
newbie = make_user("Nora", "nora@contact-test.pt", "+351916333004", password=None)
studio = make_user(
    "Studio", "studio@contact-test.pt", "+351916333005", password="studio-pass-1", role=UserRole.SUPER_ADMIN
)
session.commit()
eva_auth = auth_for(eva)

# --- Email, step 1 ---
r = client.post("/v1/auth/me/email", headers=eva_auth, json={"current_password": "wrong", "new_email": NEW_EMAIL})
check("wrong password -> 400 (she stays logged in)", r.status_code == 400, r.status_code)
r = client.post(
    "/v1/auth/me/email", headers=eva_auth, json={"current_password": "eva-password-1", "new_email": "not-an-email"}
)
check("invalid email -> 422", r.status_code == 422, r.status_code)
r = client.post(
    "/v1/auth/me/email",
    headers=eva_auth,
    json={"current_password": "eva-password-1", "new_email": " EVA@contact-test.pt "},
)
check("her own email (other case, spaces) -> 400", r.status_code == 400, r.text)
r = client.post(
    "/v1/auth/me/email", headers=eva_auth, json={"current_password": "eva-password-1", "new_email": TAKEN_EMAIL}
)
check("an email of another client -> 409", r.status_code == 409, r.status_code)
r = client.post("/v1/auth/me/email", json={"current_password": "eva-password-1", "new_email": NEW_EMAIL})
check("not logged in -> 401", r.status_code == 401, r.status_code)
r = client.post(
    "/v1/auth/me/email",
    headers=auth_for(newbie),
    json={"current_password": "anything", "new_email": "nora.new@contact-test.pt"},
)
check("a client without a password -> 409", r.status_code == 409, r.status_code)
check("no code sent so far", codes == {}, codes)

r = client.post(
    "/v1/auth/me/email", headers=eva_auth, json={"current_password": "eva-password-1", "new_email": NEW_EMAIL}
)
check(
    "start -> 200, masked new email",
    r.status_code == 200 and r.json()["detail"]["sent_to"] == "e***@contact-test.pt",
    r.text,
)
check("the code went to the NEW email", list(codes) == [NEW_EMAIL], codes)
check("nothing changed yet", client.get("/v1/auth/me", headers=eva_auth).json()["detail"]["email"] == EVA_EMAIL)
r = client.post(
    "/v1/auth/me/email", headers=eva_auth, json={"current_password": "eva-password-1", "new_email": NEW_EMAIL}
)
check("asking again at once -> 429", r.status_code == 429, r.status_code)

# --- Email, step 2 ---
code = codes[NEW_EMAIL]
wrong = "000000" if code != "000000" else "111111"
r = client.post("/v1/auth/me/email/confirm", headers=eva_auth, json={"code": wrong})
check("wrong code -> 400", r.status_code == 400, r.status_code)
r = client.post("/v1/auth/me/email/confirm", headers=auth_for(rita), json={"code": code})
check("her code does not work for another client -> 400", r.status_code == 400, r.status_code)
r = client.post("/v1/auth/me/email/confirm", headers=eva_auth, json={"code": code})
check("right code -> 200 with the new email", r.status_code == 200 and r.json()["detail"]["email"] == NEW_EMAIL, r.text)
check("still verified", r.json()["detail"]["email_verified"] is True, r.text)
check("the OLD email got a notice", email_notices == [(EVA_EMAIL, "e***@contact-test.pt")], email_notices)
r = client.post("/v1/auth/me/email/confirm", headers=eva_auth, json={"code": code})
check("the same code cannot be used twice -> 400", r.status_code == 400, r.status_code)
codes.clear()
r = client.post("/v1/auth/password/forgot", json={"phone": EVA_PHONE})
check("the password reset now goes to the new email", r.status_code == 200 and list(codes) == [NEW_EMAIL], codes)

# --- Phone ---
r = client.post("/v1/auth/me/phone", headers=eva_auth, json={"current_password": "wrong", "new_phone": NEW_PHONE})
check("wrong password -> 400", r.status_code == 400, r.status_code)
r = client.post("/v1/auth/me/phone", headers=eva_auth, json={"current_password": "eva-password-1", "new_phone": "12"})
check("invalid phone -> 422", r.status_code == 422, r.status_code)
r = client.post(
    "/v1/auth/me/phone", headers=eva_auth, json={"current_password": "eva-password-1", "new_phone": EVA_PHONE}
)
check("her own phone -> 400", r.status_code == 400, r.status_code)
r = client.post(
    "/v1/auth/me/phone", headers=eva_auth, json={"current_password": "eva-password-1", "new_phone": TAKEN_PHONE}
)
check("a phone of another client -> 409", r.status_code == 409, r.status_code)
r = client.post(
    "/v1/auth/me/phone", headers=eva_auth, json={"current_password": "eva-password-1", "new_phone": NEW_PHONE}
)
check("change -> 200 with the new phone", r.status_code == 200 and r.json()["detail"]["phone"] == NEW_PHONE, r.text)
check("a notice went to her (new) email", phone_notices == [(NEW_EMAIL, "+351******003")], phone_notices)
login_old = client.post("/v1/auth/login", json={"phone": EVA_PHONE, "password": "eva-password-1"})
login_new = client.post("/v1/auth/login", json={"phone": NEW_PHONE, "password": "eva-password-1"})
check("the old phone no longer logs in", login_old.status_code == 401, login_old.status_code)
check("the new phone logs in", login_new.status_code == 200, login_new.status_code)

# The studio too.
r = client.post(
    "/v1/auth/me/phone",
    headers=auth_for(studio),
    json={"current_password": "studio-pass-1", "new_phone": "+351916333006"},
)
check("the studio changes hers -> 200", r.status_code == 200, r.text)

transaction.rollback()
connection.close()
