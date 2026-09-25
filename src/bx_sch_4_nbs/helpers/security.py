import hashlib

from cryptography.fernet import Fernet
from pwdlib import PasswordHash

from bx_sch_4_nbs.config import settings

password_hasher = PasswordHash.recommended()
email_cipher = Fernet(settings.encryption_key.encode())


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_email(email: str) -> str:
    normalized_email = normalize_email(email)
    return hashlib.sha256(normalized_email.encode()).hexdigest()


def encrypt_email(email: str) -> str:
    normalized_email = normalize_email(email)
    return email_cipher.encrypt(normalized_email.encode()).decode()


def decrypt_email(encrypted_email: str) -> str:
    return email_cipher.decrypt(encrypted_email.encode()).decode()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)