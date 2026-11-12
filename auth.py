"""
auth.py — oddiy admin autentifikatsiyasi (sessiya cookie asosida).

Sozlamalar muhit o'zgaruvchilari orqali beriladi:
    ADMIN_USERNAME   (standart: admin)
    ADMIN_PASSWORD   (standart: admin123  — ishlab chiqarishda ALBATTA o'zgartiring)
    SECRET_KEY       (bo'lmasa .secret_key faylida avtomatik yaratiladi)
"""
import hmac
import os
import secrets
import time

import config
import store

ADMIN_HASH_KEY = "admin_password_hash"
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
USING_DEFAULT_PASSWORD = "ADMIN_PASSWORD" not in os.environ

_SECRET_PATH = os.path.join(config.BASE_DIR, ".secret_key")


def load_secret_key() -> str:
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    if os.path.exists(_SECRET_PATH):
        with open(_SECRET_PATH, encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    with open(_SECRET_PATH, "w", encoding="utf-8") as fh:
        fh.write(key)
    return key


def check_credentials(username: str, password: str) -> bool:
    # Ikkala taqqoslash ham doim bajariladi (vaqt bo'yicha farq bildirmaslik uchun).
    user_ok = hmac.compare_digest(username.encode(), ADMIN_USERNAME.encode())
    override = store.get_setting(ADMIN_HASH_KEY)  # admin paneldan o'zgartirilgan parol
    if override:
        pass_ok = verify_password(password, override)
    else:
        pass_ok = hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode())
    return user_ok and pass_ok


def admin_password_is_default() -> bool:
    return USING_DEFAULT_PASSWORD and not store.get_setting(ADMIN_HASH_KEY)


# --- Brute-force'dan himoya: IP bo'yicha urinishlarni cheklash -------------
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300
_failed: dict[str, list[float]] = {}


def _recent(ip: str) -> list[float]:
    now = time.time()
    attempts = [t for t in _failed.get(ip, []) if now - t < _WINDOW_SECONDS]
    _failed[ip] = attempts
    return attempts


def is_locked(ip: str) -> bool:
    return len(_recent(ip)) >= _MAX_ATTEMPTS


def register_failure(ip: str) -> None:
    _recent(ip).append(time.time())


def reset_failures(ip: str) -> None:
    _failed.pop(ip, None)


# --- Oddiy foydalanuvchilar: ro'yxatdan o'tish va parol xeshlash -----------
import hashlib
import re

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
MIN_PASSWORD_LEN = 8


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    return len(email) <= 254 and bool(EMAIL_RE.match(email))


def valid_password(password: str) -> bool:
    return MIN_PASSWORD_LEN <= len(password) <= 128


def validate_registration(username: str, email: str, password: str):
    """Xato kodini (yoki None) qaytaradi."""
    if not USERNAME_RE.match(username):
        return "username"
    if username.lower() == ADMIN_USERNAME.lower():
        return "exists"
    if not valid_email(email):
        return "email"
    if not valid_password(password):
        return "password"
    return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except ValueError:
        return False


# Umumiy cheklagich: (bucket, kalit) bo'yicha `window` soniyada `limit` ta urinish
_buckets: dict[tuple[str, str], list[float]] = {}


def rate_ok(bucket: str, key: str, limit: int, window: int) -> bool:
    now = time.time()
    attempts = [t for t in _buckets.get((bucket, key), []) if now - t < window]
    if len(attempts) >= limit:
        _buckets[(bucket, key)] = attempts
        return False
    attempts.append(now)
    _buckets[(bucket, key)] = attempts
    return True


# --- Email tasdiqlash kodlari ----------------------------------------------
CODE_TTL_SECONDS = 10 * 60
CODE_RESEND_COOLDOWN = 60
CODE_MAX_ATTEMPTS = 5


def generate_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_code(email: str, purpose: str, code: str) -> str:
    key = load_secret_key().encode()
    return hmac.new(key, f"{email}|{purpose}|{code}".encode(), hashlib.sha256).hexdigest()


# Mavjud bo'lmagan login uchun taqqoslash xeshi
DUMMY_HASH = hash_password(secrets.token_hex(8))
