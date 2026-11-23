import hashlib
import hmac
import secrets

import phonenumbers
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

from bx_sch_4_nbs.config import settings

password_hasher = PasswordHash.recommended()
cipher = Fernet(settings.encryption_key.encode())
hash_pepper = settings.hash_pepper.encode()


def _hash(value: str) -> str:
    return hmac.new(hash_pepper, value.encode(), hashlib.sha256).hexdigest()


def _encrypt(value: str) -> str:
    return cipher.encrypt(value.encode()).decode()


def _decrypt(encrypted_value: str) -> str:
    return cipher.decrypt(encrypted_value.encode()).decode()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_email(email: str) -> str:
    return _hash(normalize_email(email))


def encrypt_email(email: str) -> str:
    return _encrypt(normalize_email(email))


def decrypt_email(encrypted_email: str) -> str:
    return _decrypt(encrypted_email)


def email_or_none(encrypted_email: str | None) -> str | None:
    """The email, or None for a client who has not given it yet (see User.email_encrypted)."""
    return _decrypt(encrypted_email) if encrypted_email else None


def required_email(encrypted_email: str | None) -> str:
    """For accounts that always have an email (active clients, the studio, a client who just checked in)."""
    if not encrypted_email:
        raise RuntimeError("This account has no email.")
    return _decrypt(encrypted_email)


def normalize_phone(phone: str) -> str:
    try:
        parsed = phonenumbers.parse(phone, None)
    except phonenumbers.NumberParseException as error:
        raise ValueError("Invalid phone number, use the international format (e.g. +351912345678)") from error

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Invalid phone number, use the international format (e.g. +351912345678)")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def hash_phone(phone: str) -> str:
    return _hash(normalize_phone(phone))


def encrypt_phone(phone: str) -> str:
    return _encrypt(normalize_phone(phone))


def decrypt_phone(encrypted_phone: str) -> str:
    return _decrypt(encrypted_phone)


def phone_or_none(encrypted_phone: str | None) -> str | None:
    return _decrypt(encrypted_phone) if encrypted_phone else None


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_verification_code(code: str) -> str:
    return _hash(code)


def verification_code_matches(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_verification_code(code), code_hash)
