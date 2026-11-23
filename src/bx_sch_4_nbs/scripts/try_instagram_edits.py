"""The studio fixes a wrong Instagram: in the pre-approved list, or in the client's profile.
The two stay in step, so a typo never needs a second account (nor a delete in the database)."""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import PreApprovedInstagram, User
from bx_sch_4_nbs.database.types import UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.main import app

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


def handles() -> set[str]:
    return {e["instagram"] for e in client.get("/v1/admin/pre-approved-instagrams", headers=ADMIN).json()["detail"]}


# --- A handle only (no account yet) ---
r = client.post("/v1/admin/pre-approved-instagrams", json={"instagram": "typo.only.handle"}, headers=ADMIN)
only_id = r.json()["detail"]["id"]
r = client.put(f"/v1/admin/pre-approved-instagrams/{only_id}", json={"instagram": "@Fixed.Only.Handle"}, headers=ADMIN)
check(
    "fix a handle -> 200, normalised",
    r.status_code == 200 and r.json()["detail"]["instagram"] == "fixed.only.handle",
    r.text,
)
check(
    "...the list has the new one, not the typo",
    "fixed.only.handle" in handles() and "typo.only.handle" not in handles(),
)
check("...no account involved", r.json()["detail"]["client_id"] is None, r.text)

# --- A regular client created with a typo (the Sara case) ---
r = client.post(
    "/v1/admin/pre-approved-instagrams", json={"instagram": "sara.typo.test", "client": {"name": "Sara"}}, headers=ADMIN
)
entry_id, sara_id = r.json()["detail"]["id"], r.json()["detail"]["client_id"]
r = client.put(f"/v1/admin/pre-approved-instagrams/{entry_id}", json={"instagram": "sara.right.test"}, headers=ADMIN)
check(
    "fix the handle of a regular -> 200, her account is returned",
    r.status_code == 200 and r.json()["detail"]["client_id"] == sara_id,
    r.text,
)
session.expire_all()
sara = session.get(User, sara_id)
check("...her account now has the right handle too", sara is not None and sara.instagram == "sara.right.test")

# --- From the client's profile ---
r = client.put(f"/v1/admin/clients/{sara_id}/instagram", json={"instagram": "sara.final.test"}, headers=ADMIN)
check(
    "fix it from her profile -> 200",
    r.status_code == 200 and r.json()["detail"]["client"]["instagram"] == "sara.final.test",
    r.text,
)
check(
    "...and the pre-approved entry follows, so she can still check in",
    "sara.final.test" in handles() and "sara.right.test" not in handles(),
)
r = client.put(f"/v1/admin/clients/{sara_id}/instagram", json={"instagram": "sara.final.test"}, headers=ADMIN)
check("the same handle again -> 200, nothing changes", r.status_code == 200, r.status_code)

# --- Conflicts and errors ---
other = User(name="Other", last_name="Account", instagram="taken.by.other")
session.add(other)
session.add(PreApprovedInstagram(instagram="taken.in.list"))
session.commit()
r = client.put(f"/v1/admin/clients/{sara_id}/instagram", json={"instagram": "taken.by.other"}, headers=ADMIN)
check("a handle of another account -> 409", r.status_code == 409, r.status_code)
r = client.put(f"/v1/admin/pre-approved-instagrams/{entry_id}", json={"instagram": "taken.in.list"}, headers=ADMIN)
check("a handle already in the list -> 409", r.status_code == 409, r.status_code)
session.expire_all()
sara = session.get(User, sara_id)
check("...and nothing changed after the conflicts", sara is not None and sara.instagram == "sara.final.test")
r = client.put(f"/v1/admin/clients/{sara_id}/instagram", json={"instagram": "not valid"}, headers=ADMIN)
check("an invalid handle -> 422", r.status_code == 422, r.status_code)
check(
    "a missing entry -> 404",
    client.put("/v1/admin/pre-approved-instagrams/999999", json={"instagram": "x.y"}, headers=ADMIN).status_code == 404,
)
check(
    "a missing client -> 404",
    client.put("/v1/admin/clients/999999/instagram", json={"instagram": "x.y"}, headers=ADMIN).status_code == 404,
)
check(
    "not the studio -> 401/403",
    client.put(f"/v1/admin/clients/{sara_id}/instagram", json={"instagram": "x.y"}).status_code in (401, 403),
)

transaction.rollback()
connection.close()
