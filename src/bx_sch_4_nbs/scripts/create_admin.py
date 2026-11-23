from getpass import getpass
from typing import NoReturn

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlmodel import Session, or_, select

from bx_sch_4_nbs.database.helpers import engine
from bx_sch_4_nbs.database.models import User
from bx_sch_4_nbs.database.types import UserRole
from bx_sch_4_nbs.helpers.security import (
    encrypt_email,
    encrypt_phone,
    hash_email,
    hash_password,
    hash_phone,
    normalize_email,
    normalize_phone,
)


def fail(message: str) -> NoReturn:
    """Every way out without an admin says so clearly, whatever went wrong."""
    raise SystemExit(f"Erro: {message}\nAdmin não criada.")


def ask() -> tuple[str, str, str, str, str]:
    name = input("Nome: ").strip()
    last_name = input("Apelido: ").strip()
    if not name or not last_name:
        fail("o nome e o apelido são obrigatórios.")

    try:
        email = normalize_email(TypeAdapter(EmailStr).validate_python(input("Email: ").strip()))
    except ValidationError:
        fail("o email não é válido.")

    try:
        phone = normalize_phone(input("Telefone (com código do país, ex: +351912345678): "))
    except ValueError as error:
        fail(str(error))

    password = getpass("Palavra-passe: ")
    if len(password) < 8:
        fail("a palavra-passe precisa de pelo menos 8 caracteres.")
    if password != getpass("Confirme a palavra-passe: "):
        fail("as palavras-passe não coincidem.")

    return name, last_name, email, phone, password


def main() -> None:
    try:
        name, last_name, email, phone, password = ask()
    except KeyboardInterrupt, EOFError:
        fail("cancelado.")

    try:
        with Session(engine) as session:
            existing = session.exec(
                select(User).where(or_(User.phone_hash == hash_phone(phone), User.email_hash == hash_email(email)))
            ).first()
            if existing is not None:
                fail("já existe uma conta com esse telefone ou email.")

            admin = User(
                name=name,
                last_name=last_name,
                email_encrypted=encrypt_email(email),
                email_hash=hash_email(email),
                phone_encrypted=encrypt_phone(phone),
                phone_hash=hash_phone(phone),
                password_hash=hash_password(password),
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                email_verified=True,
            )
            session.add(admin)
            session.commit()
            print(f"Admin criada com id {admin.id}.")
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 - any database problem ends the same way, with a clear message
        fail(f"não foi possível gravar na base de dados ({type(error).__name__}: {error}).")


if __name__ == "__main__":
    main()
