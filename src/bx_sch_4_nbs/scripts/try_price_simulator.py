from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.queries.prices import calculate_price
from bx_sch_4_nbs.database.types import NailArtLevel, NailSize, Service
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
URL = "/v1/prices/simulate"


def check(label: str, ok: bool, detail: object = "") -> None:
    print("OK    " if ok else "ERRO  ", label, detail if not ok else "")


def simulate(**params: object) -> tuple[int, dict]:
    r = client.get(URL, params=params)  # no Authorization header: it is public
    return r.status_code, r.json()


# --- Same price as the real calculation ---
code, body = simulate(service="Application", nail_size="L", nail_art_level="Level 2", broken_nails=2)
expected = calculate_price(
    session,
    service=Service.APPLICATION,
    nail_size=NailSize.LARGE,
    nail_art_level=NailArtLevel.LEVEL_2,
    broken_nails=2,
)
check("works without login -> 200", code == 200, body)
check("application: same price as calculate_price", Decimal(body["detail"]["estimated_price"]) == expected, body)
check("application: no note", body["detail"]["note"] is None, body)
extras = [e["description"] for e in body["detail"]["possible_extras"]]
check("application: only the extra charm as a possible extra", extras == ["Extra charm"], extras)

code, body = simulate(service="Application", nail_size="L", nail_art_level="Level 2", has_other_professional_nails=True)
extras = [e["description"] for e in body["detail"]["possible_extras"]]
check(
    "nails from another professional: removal as a possible extra", len(extras) == 2 and "removal" in extras[0], extras
)

code, body = simulate(service="Maintenance", nail_size="M", nail_art_level="Level 1")
expected = calculate_price(
    session, service=Service.MAINTENANCE, nail_size=NailSize.MEDIUM, nail_art_level=NailArtLevel.LEVEL_1
)
check("maintenance: maintenance price", Decimal(body["detail"]["estimated_price"]) == expected, body)
check("maintenance: stays maintenance", body["detail"]["service"] == "Maintenance", body)
check("maintenance: a note on the days rule", "days" in (body["detail"]["note"] or ""), body)

code, body = simulate(service="Removal")
expected = calculate_price(session, service=Service.REMOVAL, nail_size=None, nail_art_level=None)
check("removal: price, no extras", code == 200 and Decimal(body["detail"]["estimated_price"]) == expected, body)
check("removal: no possible extras", body["detail"]["possible_extras"] == [], body)

# --- The same rules as the booking ---
code, _ = simulate(service="Other")
check("OTHER (studio only) -> 422", code == 422, code)
code, _ = simulate(service="Application", nail_size="L")
check("application without art level -> 422", code == 422, code)
code, _ = simulate(service="Removal", nail_size="L")
check("removal with a size -> 422", code == 422, code)
code, _ = simulate(service="Application", nail_size="L", nail_art_level="Level 1", broken_nails=11)
check("more than 10 broken nails -> 422", code == 422, code)
code, _ = simulate(service="Application", nail_size="XXXL", nail_art_level="Level 1")
check("unknown size -> 422", code == 422, code)

session.close()
transaction.rollback()
connection.close()
