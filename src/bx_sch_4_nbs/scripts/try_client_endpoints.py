from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import Appointment, Policy, User
from bx_sch_4_nbs.database.queries.users import list_agenda_subscribers
from bx_sch_4_nbs.database.types import AppointmentStatus, Service, UserRole
from bx_sch_4_nbs.helpers.authentication import create_access_token
from bx_sch_4_nbs.helpers.common import utc_now
from bx_sch_4_nbs.helpers.security import encrypt_email, encrypt_phone, hash_email, hash_phone
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


def make_user(name: str, last_name: str, instagram: str, email: str, phone: str) -> User:
    user = User(
        name=name,
        last_name=last_name,
        instagram=instagram,
        email_encrypted=encrypt_email(email),
        email_hash=hash_email(email),
        phone_encrypted=encrypt_phone(phone),
        phone_hash=hash_phone(phone),
        is_active=True,
        email_verified=True,
    )
    session.add(user)
    session.flush()
    return user


admin = session.exec(select(User).where(User.role == UserRole.SUPER_ADMIN)).first()
carla = make_user("Carlota", "Zebedeu", "carlota.zz", "carlota@zz.com", "+351913000222")
dora = make_user("Dora", "Zebedeu", "dora.zz", "dora@zz.com", "+351913000333")
policy = session.exec(select(Policy)).first()
assert admin is not None and carla.id is not None and dora.id is not None
assert policy is not None and policy.id is not None
POLICY = policy.id
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
CARLA = {"Authorization": f"Bearer {create_access_token(carla)}"}
now = utc_now()
for user_id, days in ((carla.id, 5), (carla.id, -20), (dora.id, 6)):
    session.add(
        Appointment(
            user_id=user_id,
            scheduled_at=now + timedelta(days=days, minutes=3),
            status=AppointmentStatus.SCHEDULED,
            service=Service.REMOVAL,
            estimated_price=Decimal(10),
            policy_id=POLICY,
            policies_accepted_at=None,
        )
    )
session.commit()


def search(term: str, headers: dict[str, str] = ADMIN):
    return client.get("/v1/admin/clients", params={"search": term}, headers=headers)


def names(term: str) -> set[str]:
    return {row["name"] for row in search(term).json().get("detail", [])}


# --- busca de clientes (admin) ---
check("busca pelo sobrenome encontra as duas", names("Zebedeu") >= {"Carlota", "Dora"}, names("Zebedeu"))
check("busca por parte do nome", "Carlota" in names("arlot"))
check("busca pelo @, com ou sem arroba", "Dora" in names("@dora.zz") and "Dora" in names("dora.zz"))
check("busca pelo email exato", names("carlota@zz.com") == {"Carlota"}, names("carlota@zz.com"))
check("busca pelo telefone exato", names("+351913000333") == {"Dora"}, names("+351913000333"))
check("parte do email nao encontra (esta criptografado)", "Carlota" not in names("carlota@zz"))
row = next(r for r in search("Carlota").json()["detail"] if r["name"] == "Carlota")
check(
    "o resultado traz email e telefone legiveis",
    row["email"] == "carlota@zz.com" and row["phone"] == "+351913000222",
    row,
)
check("a busca nao devolve a admin", admin.id not in [r["id"] for r in search(admin.name).json().get("detail", [])])
check("busca com 1 letra: 422", search("Z").status_code == 422)
check("cliente tentando buscar: 403", search("Zebedeu", CARLA).status_code == 403)

# --- marcacoes da cliente ---
response = client.get("/v1/appointments", headers=CARLA)
rows = response.json().get("detail", [])
check("minhas marcacoes: 200", response.status_code == 200, response.text[:200])
check("so as marcacoes da propria cliente (2, nao 3)", len(rows) == 2, len(rows))
check("a mais recente primeiro", len(rows) == 2 and rows[0]["scheduled_at"] > rows[1]["scheduled_at"])
check("marcacao sem aceite das politicas aparece normalmente", rows and rows[0]["policies_accepted_at"] is None)
check("sem login: 401", client.get("/v1/appointments").status_code == 401)

# --- preferencia dos emails da agenda ---
me = client.get("/v1/auth/me", headers=CARLA).json()["detail"]
check("o /me mostra a preferencia (ligada por padrao)", me.get("wants_agenda_emails") is True, me)
check("ela esta na lista de quem recebe a agenda", carla.id in [u.id for u in list_agenda_subscribers(session)])
response = client.patch("/v1/auth/me", json={"wants_agenda_emails": False}, headers=CARLA)
check(
    "desligar os emails: 200", response.status_code == 200 and response.json()["detail"]["wants_agenda_emails"] is False
)
session.expire_all()
check("ela saiu da lista da agenda", carla.id not in [u.id for u in list_agenda_subscribers(session)])
check(
    "ligar de novo",
    client.patch("/v1/auth/me", json={"wants_agenda_emails": True}, headers=CARLA).json()["detail"][
        "wants_agenda_emails"
    ]
    is True,
)
check("corpo invalido: 422", client.patch("/v1/auth/me", json={}, headers=CARLA).status_code == 422)

transaction.rollback()
connection.close()
