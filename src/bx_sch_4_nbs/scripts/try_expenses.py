from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bx_sch_4_nbs.database.helpers import engine, get_session
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.queries import reports
from bx_sch_4_nbs.database.types import ExpenseCategory, UserRole
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
regular = session.exec(select(User).where(User.role == UserRole.USER)).first()
assert admin is not None and regular is not None
ADMIN = {"Authorization": f"Bearer {create_access_token(admin)}"}
CLIENT = {"Authorization": f"Bearer {create_access_token(regular)}"}

# A year far away, so the real data does not get in the way.
YEAR = 2099


def add(day: str, description: str, category: str, amount: str) -> dict:
    data = {"day": day, "description": description, "category": category, "amount": amount}
    return client.post("/v1/admin/expenses", headers=ADMIN, json=data).json()


# --- Validation and access ---
r = client.post("/v1/admin/expenses", headers=CLIENT, json={})
check("a client cannot add expenses -> 403", r.status_code == 403, r.status_code)
ok_body = {"day": f"{YEAR}-03-10", "description": "Géis", "category": "Products", "amount": "20.00"}
for label, change in [
    ("amount zero -> 422", {"amount": "0"}),
    ("negative amount -> 422", {"amount": "-5"}),
    ("three decimal places -> 422", {"amount": "1.234"}),
    ("blank description -> 422", {"description": "   "}),
    ("unknown category -> 422", {"category": "Holidays"}),
]:
    r = client.post("/v1/admin/expenses", headers=ADMIN, json={**ok_body, **change})
    check(label, r.status_code == 422, r.text)

# --- Create, list, change, remove ---
r = client.post("/v1/admin/expenses", headers=ADMIN, json={**ok_body, "description": "  Géis UV  "})
created = r.json()["detail"]
check("create -> 201", r.status_code == 201, r.text)
check("the description is trimmed", created["description"] == "Géis UV", created)

add(f"{YEAR}-03-31", "Renda", "Bills", "250.00")
add(f"{YEAR}-03-15", "Limas", "Material", "12.50")
add(f"{YEAR}-04-01", "Luz", "Bills", "40.00")

r = client.get("/v1/admin/expenses", headers=ADMIN, params={"year": YEAR, "month": 3})
march = r.json()["detail"]
check("list of March: 3 expenses, by day", [e["day"][8:] for e in march] == ["10", "15", "31"], march)

r = client.put(
    f"/v1/admin/expenses/{created['id']}",
    headers=ADMIN,
    json={**ok_body, "description": "Géis UV", "amount": "25.00"},
)
check(
    "change -> 200, new amount", r.status_code == 200 and Decimal(r.json()["detail"]["amount"]) == Decimal(25), r.text
)
r = client.put("/v1/admin/expenses/999999", headers=ADMIN, json=ok_body)
check("change an unknown expense -> 404", r.status_code == 404, r.status_code)

# --- The report ---
r = client.get("/v1/admin/reports", headers=ADMIN, params={"year": YEAR})
months = {m["month"]: m for m in r.json()["detail"]["months"]}
m3, m4, m5 = months[3], months[4], months[5]
check("March expenses = 25 + 250 + 12.50", Decimal(m3["expenses"]) == Decimal("287.50"), m3["expenses"])
by_category = {c["category"]: Decimal(c["amount"]) for c in m3["expenses_by_category"]}
check(
    "March by category",
    by_category == {"Products": Decimal(25), "Bills": Decimal(250), "Material": Decimal("12.50")},
    by_category,
)
check(
    "March profit = income - expenses",
    Decimal(m3["profit"]) == Decimal(m3["total_revenue"]) - Decimal("287.50"),
    m3,
)
check("31 March stays in March, 1 April in April", Decimal(m4["expenses"]) == Decimal(40), m4["expenses"])
check("a month without expenses: 0", Decimal(m5["expenses"]) == 0 and m5["expenses_by_category"] == [], m5)

query_report = reports.year_report(session, YEAR)[2]
check("query: profit property", query_report.profit == query_report.total_revenue - Decimal("287.50"))
check(
    "query: categories",
    query_report.expenses_by_category[ExpenseCategory.BILLS] == Decimal(250),
    query_report.expenses_by_category,
)

# --- Remove ---
r = client.delete(f"/v1/admin/expenses/{created['id']}", headers=ADMIN)
check("remove -> 200", r.status_code == 200, r.text)
r = client.delete(f"/v1/admin/expenses/{created['id']}", headers=ADMIN)
check("remove again -> 404", r.status_code == 404, r.status_code)
r = client.get("/v1/admin/reports", headers=ADMIN, params={"year": YEAR})
check("the report follows", Decimal(r.json()["detail"]["months"][2]["expenses"]) == Decimal("262.50"), r.text)

session.close()
transaction.rollback()
connection.close()
