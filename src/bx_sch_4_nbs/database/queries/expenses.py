from datetime import date
from decimal import Decimal

from sqlmodel import Session, col, select

from bx_sch_4_nbs.database.exceptions import ResourceDoesNotExistError
from bx_sch_4_nbs.database.models import Expense
from bx_sch_4_nbs.database.types import ExpenseCategory


def list_expenses(session: Session, first_day: date, last_day: date) -> list[Expense]:
    return list(
        session.exec(
            select(Expense)
            .where(col(Expense.day).between(first_day, last_day))
            .order_by(col(Expense.day), col(Expense.id))
        ).all()
    )


def get_expense(session: Session, expense_id: int) -> Expense:
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise ResourceDoesNotExistError(f"Expense {expense_id} does not exist.")
    return expense


def create_expense(
    session: Session, day: date, description: str, category: ExpenseCategory, amount: Decimal
) -> Expense:
    expense = Expense(day=day, description=description, category=category, amount=amount)
    session.add(expense)
    session.flush()
    return expense


def update_expense(
    session: Session, expense_id: int, day: date, description: str, category: ExpenseCategory, amount: Decimal
) -> Expense:
    expense = get_expense(session, expense_id)
    expense.day = day
    expense.description = description
    expense.category = category
    expense.amount = amount
    session.add(expense)
    session.flush()
    return expense


def delete_expense(session: Session, expense_id: int) -> None:
    session.delete(get_expense(session, expense_id))
    session.flush()
