import hashlib
import hmac

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


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)
