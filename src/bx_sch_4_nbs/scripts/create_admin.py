from getpass import getpass

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
    normalize_phone,
)


def main() -> None:
    name = input("Nome: ").strip()
    last_name = input("Sobrenome: ").strip()
    email = input("Email: ")
    try:
        phone = normalize_phone(input("Telefone (com código do país, ex: +351912345678): "))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    password = getpass("Senha: ")

    if len(password) < 8:
        raise SystemExit("A senha precisa ter pelo menos 8 caracteres.")
    if password != getpass("Confirme a senha: "):
        raise SystemExit("As senhas não conferem.")

    with Session(engine) as session:
        existing = session.exec(
            select(User).where(or_(User.phone_hash == hash_phone(phone), User.email_hash == hash_email(email)))
        ).first()
        if existing is not None:
            raise SystemExit("Já existe um usuário com esse telefone ou email.")

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


if __name__ == "__main__":
    main()
