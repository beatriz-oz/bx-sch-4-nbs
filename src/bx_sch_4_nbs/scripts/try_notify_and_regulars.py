"""The "agenda is open" email is sent by a button (not when publishing), and a pre-approved
regular client can get her account at once, approved, so she only creates a password."""

from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import bx_sch_4_nbs.routers.admin as admin_router
import bx_sch_4_nbs.routers.auth as auth_router
from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, PreApprovedInstagram, User
from bx_sch_4_nbs.database.queries.users import get_user_by_phone
from bx_sch_4_nbs.database.types import AppointmentStatus, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import to_studio_time, utc_now
from bx_sch_4_nbs.main import app
from bx_sch_4_nbs.scripts import process_appointments

agenda_emails: list[tuple] = []
codes: dict[str, str] = {}
setattr(admin_router, "send_agenda_published", lambda *args: agenda_emails.append(args))  # noqa: B010
setattr(auth_router, "send_verification_code", lambda to, code: codes.__setitem__(to, code))  # noqa: B010
booked_emails: list[tuple] = []
setattr(admin_router, "send_booked_by_studio_notification", lambda *args: booked_emails.append(args))  # noqa: B010

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


def check(label: str, ok: bool, detail: object = "") -> None:
    print("OK    " if ok else "ERRO  ", label, detail if not ok else "")


admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
assert admin is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}

# --- Publishing sends nothing; the button does ---
YEAR, MONTH = 2098, 3
r = client.post("/v1/admin/published-months", json={"year": YEAR, "month": MONTH}, headers=ADMIN)
check("publish -> 201", r.status_code == 201, r.text)
check("publish: no email sent", agenda_emails == [], agenda_emails)
check("publish: not notified yet", r.json()["detail"]["notified_at"] is None, r.text)

agenda = client.get("/v1/admin/agenda", params={"year": YEAR, "month": MONTH}, headers=ADMIN).json()["detail"]
check("agenda shows published, not notified", agenda["published_at"] is not None and agenda["notified_at"] is None)

r = client.post(f"/v1/admin/published-months/{YEAR}/{MONTH + 1}/notify", headers=ADMIN)
check("notify an unpublished month -> 404", r.status_code == 404, r.status_code)
check("...and no email", agenda_emails == [], agenda_emails)

r = client.post(f"/v1/admin/published-months/{YEAR}/{MONTH}/notify", headers=ADMIN)
detail = r.json().get("detail", {})
check("notify -> 200 with the count and the time", r.status_code == 200 and detail.get("notified_at"), r.text)
check(
    "the email went to the agenda subscribers",
    len(agenda_emails) == 1
    and agenda_emails[0][1:] == (YEAR, MONTH)
    and len(agenda_emails[0][0]) == detail["notified_clients"],
    agenda_emails,
)
agenda = client.get("/v1/admin/agenda", params={"year": YEAR, "month": MONTH}, headers=ADMIN).json()["detail"]
check("agenda now shows when it was notified", agenda["notified_at"] is not None, agenda.get("notified_at"))
r = client.post(f"/v1/admin/published-months/{YEAR}/{MONTH}/notify", headers=ADMIN)
check("it can be sent again", r.status_code == 200 and len(agenda_emails) == 2, r.status_code)
check(
    "a client cannot notify -> 401/403",
    client.post(f"/v1/admin/published-months/{YEAR}/{MONTH}/notify").status_code in (401, 403),
)

# --- Pre-approve only the handle: no account ---
r = client.post("/v1/admin/pre-approved-instagrams", json={"instagram": "just.handle.regular"}, headers=ADMIN)
check("handle only -> 201, no account", r.status_code == 201 and r.json()["detail"]["client_id"] is None, r.text)
check("no user created", session.exec(select(User).where(User.instagram == "just.handle.regular")).first() is None)

# --- Pre-approve a regular client with her details ---
PHONE, EMAIL = "+351917444001", "lia@regular-test.pt"
body = {
    "instagram": "@Lia.Regular",
    "client": {"name": "Lia", "last_name": "Regular", "email": EMAIL, "phone": PHONE},
}
r = client.post("/v1/admin/pre-approved-instagrams", json=body, headers=ADMIN)
detail = r.json().get("detail", {})
check("with details -> 201 and the account id", r.status_code == 201 and detail.get("client_id"), r.text)
check("the handle was normalised", detail.get("instagram") == "lia.regular", detail)
lia = session.get(User, detail.get("client_id"))
check(
    "her account: approved, no password yet, email not verified",
    lia is not None
    and lia.approved_at is not None
    and not lia.is_active
    and lia.password_hash is None
    and not lia.email_verified,
)
pending = client.get("/v1/admin/clients/overview", params={"group": "pending"}, headers=ADMIN).json()["detail"]
check(
    "she is in the pending clients, approved",
    any(c["id"] == detail.get("client_id") and c["approved"] for c in pending),
)
found = client.get("/v1/admin/clients", params={"search": "Lia"}, headers=ADMIN)
check(
    "the studio finds her to book",
    found.status_code == 200 and any(c["id"] == detail.get("client_id") for c in found.json()["detail"]),
    found.text[:200],
)

# She only creates the password: code by email, then the password.
r = client.post("/v1/auth/activation/start", json={"phone": PHONE})
check("activation start -> 200 (she is approved)", r.status_code == 200, r.text)
r = client.post(
    "/v1/auth/activation/confirm", json={"phone": PHONE, "code": codes.get(EMAIL, ""), "password": "lia-password-1"}
)
check("she creates her password -> 200", r.status_code == 200 and "access_token" in r.text, r.text)
session.expire_all()
lia = get_user_by_phone(session, PHONE)
check("now active, email verified", lia is not None and lia.is_active and lia.email_verified)

# Problems roll everything back.
r = client.post(
    "/v1/admin/pre-approved-instagrams",
    json={
        "instagram": "other.regular",
        "client": {"name": "X", "last_name": "Y", "email": "x@regular-test.pt", "phone": PHONE},
    },
    headers=ADMIN,
)
check("a phone already registered -> 409", r.status_code == 409, r.status_code)
listed = [e["instagram"] for e in client.get("/v1/admin/pre-approved-instagrams", headers=ADMIN).json()["detail"]]
check("...and the handle was not added either", "other.regular" not in listed, listed)
r = client.post(
    "/v1/admin/pre-approved-instagrams",
    json={
        "instagram": "bad.regular",
        "client": {"name": "X", "last_name": "Y", "email": "nope", "phone": "+351917444002"},
    },
    headers=ADMIN,
)
check("an invalid email -> 422", r.status_code == 422, r.status_code)

# --- A regular client known only by her Instagram ---
r = client.post(
    "/v1/admin/pre-approved-instagrams", json={"instagram": "mia.only", "client": {"name": "Mia"}}, headers=ADMIN
)
mia_id = r.json().get("detail", {}).get("client_id")
check("only the Instagram and the name -> 201 with an account", r.status_code == 201 and mia_id, r.text)
mia = session.get(User, mia_id)
check(
    "her account: no email, no phone, approved",
    mia is not None and mia.email_encrypted is None and mia.phone_encrypted is None and mia.approved_at is not None,
)
r = client.post(
    "/v1/admin/pre-approved-instagrams", json={"instagram": "noa.only", "client": {"name": "Noa"}}, headers=ADMIN
)
check("a second one without email or phone also works (no clash)", r.status_code == 201, r.text)
pending = client.get("/v1/admin/clients/overview", params={"group": "pending"}, headers=ADMIN).json()["detail"]
row = next((c for c in pending if c["id"] == mia_id), {})
check(
    "she is in the pending clients, email and phone empty", row.get("email") is None and row.get("phone") is None, row
)
found = client.get("/v1/admin/clients", params={"search": "mia.only"}, headers=ADMIN).json()["detail"]
check("the studio finds her by the Instagram", any(c["id"] == mia_id for c in found), found)

# The studio books for her: no email, there is none to send to.
now = utc_now()
when = to_studio_time(now + timedelta(days=45)).replace(hour=10, minute=41, second=0, microsecond=0)
r = client.post(
    "/v1/admin/appointments",
    json={"scheduled_at": when.isoformat(), "service": "Removal", "estimated_price": "15", "user_id": mia_id},
    headers=ADMIN,
)
booked_id = r.json().get("detail", {}).get("id")
check("the studio books for her -> 201", r.status_code == 201, r.text[:300])
check("...and no email is attempted", booked_emails == [], booked_emails)

# The reminder skips her (no email) and stays unsent, to go out if she checks in in time.
policy = session.exec(select(Policy)).first()
assert policy is not None and policy.id is not None
soon = Appointment(
    user_id=mia_id,
    scheduled_at=now + timedelta(hours=20, minutes=7),
    status=AppointmentStatus.SCHEDULED,
    service=Service.REMOVAL,
    estimated_price=Decimal(15),
    policy_id=policy.id,
)
session.add(soon)
session.commit()
reminders: list[str] = []
setattr(process_appointments, "send_attendance_reminder", lambda to, *args: reminders.append(to) or True)  # noqa: B010
process_appointments.process_reminders(session, now)
session.refresh(soon)
check("the reminder skips her, and stays unsent", soon.reminder_sent_at is None and reminders == [], reminders)

# Her check-in with the Instagram: she gives her details, and sees the studio's booking.
MIA_EMAIL, MIA_PHONE = "mia@regular-test.pt", "+351917444009"
codes.clear()
r = client.post(
    "/v1/auth/checkin/start",
    json={"instagram": "mia.only", "name": "Mia", "last_name": "Costa", "email": MIA_EMAIL, "phone": MIA_PHONE},
)
check("check-in with her Instagram -> code sent", r.status_code == 200 and MIA_EMAIL in codes, r.text)
r = client.post("/v1/auth/checkin/verify", json={"instagram": "mia.only", "code": codes.get(MIA_EMAIL, "")})
check("code confirmed -> logged in", r.status_code == 200 and "access_token" in r.text, r.text)
mia_auth = {"Authorization": f"Bearer {r.json()['detail']['access_token']}"}
mine = client.get("/v1/appointments", headers=mia_auth).json()["detail"]
check("the appointment the studio made is in her appointments", any(a["id"] == booked_id for a in mine), mine)
me = client.get("/v1/auth/me", headers=mia_auth).json()["detail"]
check(
    "the same account, now with her details, ready for a password",
    me["id"] == mia_id
    and me["email"] == MIA_EMAIL
    and me["last_name"] == "Costa"
    and me["can_create_password"] is True,
    me,
)

# She creates her password right away (the popup), without another code.
r = client.post("/v1/auth/me/activate", headers=mia_auth, json={"password": "short"})
check("a password under 8 characters -> 422", r.status_code == 422, r.status_code)
r = client.post("/v1/auth/me/activate", headers=mia_auth, json={"password": "mia-password-1"})
check("she creates her password -> 200 with a new token", r.status_code == 200 and "access_token" in r.text, r.text)
new_auth = {"Authorization": f"Bearer {r.json()['detail']['access_token']}"}
check("now active", client.get("/v1/auth/me", headers=new_auth).json()["detail"]["is_active"] is True)
r = client.post("/v1/auth/me/activate", headers=new_auth, json={"password": "mia-password-2"})
check("activating again -> 409", r.status_code == 409, r.status_code)
r = client.post("/v1/auth/login", json={"phone": MIA_PHONE, "password": "mia-password-1"})
check("she logs in with phone and password", r.status_code == 200, r.status_code)

# A new client who is not approved yet cannot use it.
session.add(PreApprovedInstagram(instagram="new.not.approved"))
session.commit()
codes.clear()
client.post(
    "/v1/auth/checkin/start",
    json={
        "instagram": "new.not.approved",
        "name": "Rui",
        "last_name": "N",
        "email": "rui@regular-test.pt",
        "phone": "+351917444010",
    },
)
r = client.post(
    "/v1/auth/checkin/verify", json={"instagram": "new.not.approved", "code": codes.get("rui@regular-test.pt", "")}
)
rui_auth = {"Authorization": f"Bearer {r.json()['detail']['access_token']}"}
r = client.post("/v1/auth/me/activate", headers=rui_auth, json={"password": "rui-password-1"})
check("a client not approved yet -> 403", r.status_code == 403, r.status_code)

# --- Deleting pending clients: only without a password and without appointments ---
pending = client.get("/v1/admin/clients/overview", params={"group": "pending"}, headers=ADMIN).json()["detail"]
noa = next((c for c in pending if c["instagram"] == "noa.only"), {})
check("a pending client who never booked can be deleted", noa.get("can_delete") is True, noa)
r = client.delete(f"/v1/admin/clients/{noa.get('id')}", headers=ADMIN)
check("delete her -> 200", r.status_code == 200, r.text)
pending = client.get("/v1/admin/clients/overview", params={"group": "pending"}, headers=ADMIN).json()["detail"]
check("she is gone from the pending clients", all(c["id"] != noa.get("id") for c in pending))
check("her profile -> 404", client.get(f"/v1/admin/clients/{noa.get('id')}", headers=ADMIN).status_code == 404)

registered = client.get("/v1/admin/clients/overview", params={"group": "registered"}, headers=ADMIN).json()["detail"]
mia_row = next((c for c in registered if c["id"] == mia_id), {})
check("a registered client cannot be deleted (flag)", mia_row.get("can_delete") is False, mia_row)
r = client.delete(f"/v1/admin/clients/{mia_id}", headers=ADMIN)
check("...nor by the API -> 409", r.status_code == 409, r.status_code)

zoe = User(name="Zoe", last_name="Pending", instagram="zoe.pending.test", approved_at=None)
session.add(zoe)
session.flush()
assert zoe.id is not None
session.add(
    Appointment(
        user_id=zoe.id,
        scheduled_at=now - timedelta(days=40),
        status=AppointmentStatus.CANCELLED,
        service=Service.REMOVAL,
        estimated_price=Decimal(15),
        policy_id=policy.id,
    )
)
session.commit()
pending = client.get("/v1/admin/clients/overview", params={"group": "pending"}, headers=ADMIN).json()["detail"]
zoe_row = next((c for c in pending if c["id"] == zoe.id), {})
check(
    "a pending client with a (cancelled) appointment cannot be deleted (flag)",
    zoe_row.get("can_delete") is False,
    zoe_row,
)
r = client.delete(f"/v1/admin/clients/{zoe.id}", headers=ADMIN)
check("...nor by the API -> 409 with the reason", r.status_code == 409 and "history" in r.text, r.text)
check("a client who does not exist -> 404", client.delete("/v1/admin/clients/999999", headers=ADMIN).status_code == 404)
check("a client cannot delete -> 401/403", client.delete(f"/v1/admin/clients/{zoe.id}").status_code in (401, 403))

# --- Continue the activation: she checked in but closed the window before the password ---
r = client.post(
    "/v1/admin/pre-approved-instagrams", json={"instagram": "ivy.later", "client": {"name": "Ivy"}}, headers=ADMIN
)
check("another regular from her Instagram -> 201", r.status_code == 201, r.text)
IVY_EMAIL = "ivy@regular-test.pt"
codes.clear()
client.post(
    "/v1/auth/checkin/start",
    json={"instagram": "ivy.later", "name": "Ivy", "last_name": "Lima", "email": IVY_EMAIL, "phone": "+351917444011"},
)
r = client.post("/v1/auth/checkin/verify", json={"instagram": "ivy.later", "code": codes.get(IVY_EMAIL, "")})
check("her check-in works (and then she closes the popup)", r.status_code == 200, r.text)

codes.clear()
r = client.post(
    "/v1/auth/checkin/start",
    json={
        "instagram": "ivy.later",
        "name": "X",
        "last_name": "Y",
        "email": "other@regular-test.pt",
        "phone": "+351917444012",
    },
)
check("the first-appointment form again -> 409 (her details are not overwritten)", r.status_code == 409, r.status_code)

r = client.post("/v1/auth/checkin/resume", json={"instagram": "@Ivy.Later"})
check(
    "continue the activation -> code to the email she gave", r.status_code == 200 and list(codes) == [IVY_EMAIL], r.text
)
check("...masked in the answer", r.json()["detail"]["sent_to"] == "i***@regular-test.pt", r.text)
r = client.post("/v1/auth/checkin/verify", json={"instagram": "ivy.later", "code": codes.get(IVY_EMAIL, "")})
check("the code logs her in again", r.status_code == 200 and "access_token" in r.text, r.text)
ivy_auth = {"Authorization": f"Bearer {r.json()['detail']['access_token']}"}
check(
    "...ready for the password (the popup)",
    client.get("/v1/auth/me", headers=ivy_auth).json()["detail"]["can_create_password"] is True,
)
r = client.post("/v1/auth/me/activate", headers=ivy_auth, json={"password": "ivy-password-1"})
check("she creates her password -> 200", r.status_code == 200, r.text)
r = client.post("/v1/auth/checkin/resume", json={"instagram": "ivy.later"})
check("once active, nothing to continue -> 409", r.status_code == 409, r.status_code)

unknown = client.post("/v1/auth/checkin/resume", json={"instagram": "nobody.at.all"})
not_approved = client.post("/v1/auth/checkin/resume", json={"instagram": "new.not.approved"})
check(
    "unknown handle and a client not approved: the same 409 answer",
    unknown.status_code == not_approved.status_code == 409 and unknown.json() == not_approved.json(),
    (unknown.text, not_approved.text),
)
r = client.post("/v1/auth/checkin/resume", json={"instagram": "zoe.pending.test"})
check("an account never checked in (no email) -> 409", r.status_code == 409, r.status_code)

transaction.rollback()
connection.close()
