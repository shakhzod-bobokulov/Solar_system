"""
seed_demo_user.py — sinov uchun tayyor (emaili tasdiqlangan) foydalanuvchi yaratadi.

Ishga tushirish:
    python seed_demo_user.py

Faqat mahalliy sinov uchun! Ishlab chiqarishda ishlatmang.
"""
import auth
import store

DEMO_USERNAME = "bob"
DEMO_EMAIL = "bob@example.com"
DEMO_PASSWORD = "bob-demo-2026"


def main() -> None:
    store.init_db()
    store.init_users()
    password_hash = auth.hash_password(DEMO_PASSWORD)

    existing = store.get_user_by_email(DEMO_EMAIL)
    if existing:
        store.set_password(DEMO_EMAIL, password_hash)
        store.set_verified(DEMO_EMAIL)
        print(f"Yangilandi: {DEMO_USERNAME}")
    elif store.create_user(DEMO_USERNAME, DEMO_EMAIL, password_hash):
        store.set_verified(DEMO_EMAIL)
        print(f"Yaratildi: {DEMO_USERNAME}")
    else:
        print(f"'{DEMO_USERNAME}' logini band. DEMO_USERNAME ni o'zgartiring.")
        return
    print("Login va parol shu faylning yuqorisida (DEMO_USERNAME / DEMO_PASSWORD).")


if __name__ == "__main__":
    main()
