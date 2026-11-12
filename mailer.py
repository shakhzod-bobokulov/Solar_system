"""
mailer.py — tasdiqlash kodlarini email orqali yuborish (SMTP).

Muhit o'zgaruvchilari:
    SMTP_USER       yuboruvchi email (masalan: sizning@gmail.com)
    SMTP_PASSWORD   Gmail uchun "App password" (oddiy parol emas!)
    SMTP_HOST       standart: smtp.gmail.com
    SMTP_PORT       standart: 587 (STARTTLS)
    SMTP_FROM       ixtiyoriy, standart: SMTP_USER

SMTP sozlanmagan bo'lsa (ishlab chiqish rejimi) kod email o'rniga server
konsoliga chiqariladi.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
# Gmail "App password" bo'shliqlar bilan ko'rsatiladi — olib tashlaymiz
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").replace(" ", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "").strip() or SMTP_USER

CODE_TTL_MINUTES = 10

TEXTS = {
    "uz": {
        "verify": (
            "Quyosh Paneli Nazorati: email tasdiqlash kodi",
            "Sizning tasdiqlash kodingiz: {code}\n\nKod {ttl} daqiqa amal qiladi.\n"
            "Agar siz ro'yxatdan o'tmagan bo'lsangiz, bu xatni e'tiborsiz qoldiring.",
        ),
        "reset": (
            "Quyosh Paneli Nazorati: parolni tiklash kodi",
            "Parolni tiklash kodi: {code}\n\nKod {ttl} daqiqa amal qiladi.\n"
            "Agar siz so'ramagan bo'lsangiz, bu xatni e'tiborsiz qoldiring.",
        ),
    },
    "ru": {
        "verify": (
            "Мониторинг солнечных панелей: код подтверждения email",
            "Ваш код подтверждения: {code}\n\nКод действителен {ttl} минут.\n"
            "Если вы не регистрировались, проигнорируйте это письмо.",
        ),
        "reset": (
            "Мониторинг солнечных панелей: код восстановления пароля",
            "Код для восстановления пароля: {code}\n\nКод действителен {ttl} минут.\n"
            "Если вы не запрашивали восстановление, проигнорируйте это письмо.",
        ),
    },
    "en": {
        "verify": (
            "Solar Panel Monitor: email verification code",
            "Your verification code: {code}\n\nThe code is valid for {ttl} minutes.\n"
            "If you did not sign up, please ignore this email.",
        ),
        "reset": (
            "Solar Panel Monitor: password reset code",
            "Your password reset code: {code}\n\nThe code is valid for {ttl} minutes.\n"
            "If you did not request this, please ignore this email.",
        ),
    },
}


class MailError(Exception):
    pass


def is_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)


def send_code(to: str, code: str, purpose: str, lang: str) -> str:
    """Kodni yuboradi. 'sent' yoki 'dev' (konsolga chiqarildi) qaytaradi."""
    if not is_configured():
        print(f"[DEV] {purpose} kodi ({to}): {code}  — SMTP sozlanmagan, email yuborilmadi.")
        return "dev"

    subject, body = TEXTS.get(lang, TEXTS["uz"])[purpose]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg.set_content(body.format(code=code, ttl=CODE_TTL_MINUTES))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(str(exc)) from exc
    return "sent"
