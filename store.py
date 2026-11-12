"""
store.py — SQLite: tekshiruvlar, foydalanuvchilar, panellar, kodlar, sozlamalar.
Eski bazalar `init_*` chaqirilganda avtomatik yangilanadi (ustunlar qo'shiladi).
"""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import config

DB_PATH = os.environ.get("SOLAR_DB_PATH") or os.path.join(config.BASE_DIR, "checks.db")

# `thumb` (BLOB) ro'yxatlarga kirmasligi uchun ustunlar aniq sanab o'tiladi
CHECK_COLS = (
    "id, created_at, username, filename, predicted_class, category, is_clean, confidence,"
    " severity_key, power_loss, mode, panel_id, lat, lon, fb_ok, fb_class, hot_area,"
    " (thumb IS NOT NULL) AS has_thumb"
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _columns(conn, table: str) -> set:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _add_missing(conn, table: str, columns: dict) -> None:
    existing = _columns(conn, table)
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


# ---------------------------------------------------------------------------
# Tekshiruvlar
# ---------------------------------------------------------------------------
def init_db() -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                username TEXT NOT NULL,
                filename TEXT NOT NULL,
                predicted_class TEXT NOT NULL,
                category TEXT NOT NULL,
                is_clean INTEGER NOT NULL,
                confidence REAL NOT NULL,
                severity_key TEXT NOT NULL,
                power_loss REAL NOT NULL
            )
            """
        )
        _add_missing(
            conn,
            "checks",
            {
                "mode": "TEXT NOT NULL DEFAULT 'rgb'",
                "panel_id": "INTEGER",
                "lat": "REAL",
                "lon": "REAL",
                "thumb": "BLOB",
                "fb_ok": "INTEGER",  # NULL = fikr yo'q, 1 = to'g'ri, 0 = noto'g'ri
                "fb_class": "TEXT",
                "hot_area": "REAL",
            },
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_checks_user ON checks(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_checks_panel ON checks(panel_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS panels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                lat REAL,
                lon REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )


def add_check(*, username, filename, predicted_class, category, is_clean, confidence,
              severity_key, power_loss, mode="rgb", panel_id=None, lat=None, lon=None,
              thumb=None, hot_area=None) -> int:
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO checks (created_at, username, filename, predicted_class, category,"
            " is_clean, confidence, severity_key, power_loss, mode, panel_id, lat, lon,"
            " thumb, hot_area) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), username, filename, predicted_class, category, 1 if is_clean else 0,
             confidence, severity_key, power_loss, mode, panel_id, lat, lon, thumb, hot_area),
        )
        return cur.lastrowid


def list_checks(limit: int = 500, username=None, q=None, cls=None, panel_id=None) -> list[dict]:
    where, args = [], []
    if username is not None:
        where.append("username = ? COLLATE NOCASE")
        args.append(username)
    if q:
        where.append("filename LIKE ?")
        args.append(f"%{q}%")
    if cls:
        where.append("predicted_class = ?")
        args.append(cls)
    if panel_id is not None:
        where.append("panel_id = ?")
        args.append(panel_id)
    sql = f"SELECT {CHECK_COLS} FROM checks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with closing(_connect()) as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_check(check_id: int):
    with closing(_connect()) as conn:
        row = conn.execute(f"SELECT {CHECK_COLS} FROM checks WHERE id = ?", (check_id,)).fetchone()
    return dict(row) if row else None


def get_thumb(check_id: int):
    """(rasm baytlari, egasi) yoki None."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT thumb, username FROM checks WHERE id = ?", (check_id,)).fetchone()
    if not row or row["thumb"] is None:
        return None
    return bytes(row["thumb"]), row["username"]


def set_feedback(check_id: int, ok: bool, correct_class=None) -> bool:
    with closing(_connect()) as conn, conn:
        return (
            conn.execute(
                "UPDATE checks SET fb_ok = ?, fb_class = ? WHERE id = ?",
                (1 if ok else 0, None if ok else correct_class, check_id),
            ).rowcount
            > 0
        )


def delete_check(check_id: int, username=None) -> bool:
    sql, args = "DELETE FROM checks WHERE id = ?", [check_id]
    if username is not None:
        sql += " AND username = ? COLLATE NOCASE"
        args.append(username)
    with closing(_connect()) as conn, conn:
        return conn.execute(sql, args).rowcount > 0


def clear_checks() -> int:
    with closing(_connect()) as conn, conn:
        return conn.execute("DELETE FROM checks").rowcount


# ---------------------------------------------------------------------------
# Statistika (admin)
# ---------------------------------------------------------------------------
def get_stats() -> dict:
    with closing(_connect()) as conn:
        total, clean, avg_loss = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(is_clean), 0), AVG(power_loss) FROM checks"
        ).fetchone()
        by_class = conn.execute(
            "SELECT predicted_class, COUNT(*) AS n FROM checks"
            " GROUP BY predicted_class ORDER BY n DESC"
        ).fetchall()
        faults = conn.execute(
            "SELECT predicted_class, COUNT(*) AS n, AVG(power_loss) AS loss FROM checks"
            " WHERE is_clean = 0 GROUP BY predicted_class ORDER BY n DESC LIMIT 8"
        ).fetchall()
        fb_total, fb_wrong = conn.execute(
            "SELECT COUNT(fb_ok), COALESCE(SUM(CASE WHEN fb_ok = 0 THEN 1 ELSE 0 END), 0) FROM checks"
        ).fetchone()
    return {
        "total": total,
        "clean": clean,
        "faulty": total - clean,
        "avg_loss": round(avg_loss, 1) if avg_loss is not None else None,
        "by_class": [{"class": r["predicted_class"], "count": r["n"]} for r in by_class],
        "faults": [
            {"class": r["predicted_class"], "count": r["n"], "avg_loss": round(r["loss"], 1)}
            for r in faults
        ],
        "feedback": {"total": fb_total, "wrong": fb_wrong},
    }


def get_daily(days: int = 14) -> list[dict]:
    """So'nggi `days` kun bo'yicha tekshiruvlar (bo'sh kunlar 0 bilan to'ldiriladi)."""
    from datetime import date

    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT substr(created_at, 1, 10) AS d, COALESCE(SUM(is_clean), 0) AS clean, COUNT(*) AS n"
            " FROM checks WHERE substr(created_at, 1, 10) >= ? GROUP BY d",
            (start,),
        ).fetchall()
    found = {r["d"]: (r["clean"], r["n"]) for r in rows}
    result = []
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).isoformat()
        clean, n = found.get(d, (0, 0))
        result.append({"date": d, "clean": clean, "faulty": n - clean})
    return result


def get_monthly(months: int = 12) -> list[dict]:
    """So'nggi `months` oy bo'yicha tekshiruvlar (YYYY-MM)."""
    from datetime import date

    today = date.today()
    keys = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT substr(created_at, 1, 7) AS d, COALESCE(SUM(is_clean), 0) AS clean, COUNT(*) AS n"
            " FROM checks WHERE substr(created_at, 1, 7) >= ? GROUP BY d",
            (keys[0],),
        ).fetchall()
    found = {r["d"]: (r["clean"], r["n"]) for r in rows}
    out = []
    for k in keys:
        clean, n = found.get(k, (0, 0))
        out.append({"date": k, "clean": clean, "faulty": n - clean})
    return out


# ---------------------------------------------------------------------------
# Foydalanuvchilar
# ---------------------------------------------------------------------------
def init_users() -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Eski (emailsiz) foydalanuvchilar tasdiqlangan hisoblanadi (DEFAULT 1)
        _add_missing(
            conn,
            "users",
            {
                "email": "TEXT",
                "verified": "INTEGER NOT NULL DEFAULT 1",
                "blocked": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email COLLATE NOCASE)"
            " WHERE email IS NOT NULL"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS codes (
                email TEXT NOT NULL COLLATE NOCASE,
                purpose TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (email, purpose)
            )
            """
        )


def create_user(username: str, email: str, password_hash: str) -> bool:
    """Tasdiqlanmagan foydalanuvchi yaratadi. Login/email band bo'lsa False."""
    try:
        with closing(_connect()) as conn, conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, verified, created_at)"
                " VALUES (?, ?, ?, 0, ?)",
                (username, email, password_hash, _now()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_user(username: str):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_email(email: str):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def get_user_by_login(identifier: str):
    """Login yoki email bo'yicha topadi."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?", (identifier, identifier)
        ).fetchone()
    return dict(row) if row else None


def update_unverified(email: str, username: str, password_hash: str) -> bool:
    """Tasdiqlanmagan hisobni yangi login/parol bilan yangilaydi (qayta ro'yxatdan o'tish)."""
    try:
        with closing(_connect()) as conn, conn:
            return (
                conn.execute(
                    "UPDATE users SET username = ?, password_hash = ?"
                    " WHERE email = ? AND verified = 0",
                    (username, password_hash, email),
                ).rowcount
                > 0
            )
    except sqlite3.IntegrityError:
        return False


def set_verified(email: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("UPDATE users SET verified = 1 WHERE email = ?", (email,))


def set_password(email: str, password_hash: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE email = ?", (password_hash, email))


def set_blocked(user_id: int, blocked: bool) -> bool:
    with closing(_connect()) as conn, conn:
        return (
            conn.execute("UPDATE users SET blocked = ? WHERE id = ?", (1 if blocked else 0, user_id)).rowcount
            > 0
        )


def is_user_active(username: str) -> bool:
    """Foydalanuvchi mavjud va bloklanmagan bo'lsa True (sessiya har so'rovda tekshiriladi)."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT blocked FROM users WHERE username = ?", (username,)).fetchone()
    return bool(row) and not row["blocked"]


def delete_stale_unverified(hours: int = 24) -> None:
    """Tasdiqlanmagan eski hisoblar loginni band qilib turmasligi uchun o'chiriladi."""
    limit = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM users WHERE verified = 0 AND created_at < ?", (limit,))


def list_users() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT u.id, u.username, u.email, u.verified, u.blocked, u.created_at,"
            " (SELECT COUNT(*) FROM checks c WHERE c.username = u.username COLLATE NOCASE) AS checks"
            " FROM users u ORDER BY u.id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_user(user_id: int) -> bool:
    with closing(_connect()) as conn, conn:
        row = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if row["email"]:
            conn.execute("DELETE FROM codes WHERE email = ?", (row["email"],))
        return True


# ---------------------------------------------------------------------------
# Tasdiqlash kodlari
# ---------------------------------------------------------------------------
def save_code(email: str, purpose: str, code_hash: str, expires_at: float, now: float) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO codes (email, purpose, code_hash, expires_at, created_at, attempts)"
            " VALUES (?, ?, ?, ?, ?, 0)",
            (email, purpose, code_hash, expires_at, now),
        )


def get_code(email: str, purpose: str):
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM codes WHERE email = ? AND purpose = ?", (email, purpose)
        ).fetchone()
    return dict(row) if row else None


def bump_code_attempts(email: str, purpose: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE codes SET attempts = attempts + 1 WHERE email = ? AND purpose = ?",
            (email, purpose),
        )


def delete_code(email: str, purpose: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM codes WHERE email = ? AND purpose = ?", (email, purpose))


# ---------------------------------------------------------------------------
# Sozlamalar (masalan, admin parolini panel orqali o'zgartirish)
# ---------------------------------------------------------------------------
def get_setting(key: str):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


# ---------------------------------------------------------------------------
# Panellar (har panelga ID berib, vaqt bo'yicha kuzatish)
# ---------------------------------------------------------------------------
def create_panel(username: str, name: str, lat=None, lon=None) -> int:
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO panels (username, name, lat, lon, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, name, lat, lon, _now()),
        )
        return cur.lastrowid


def get_panel(panel_id: int):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM panels WHERE id = ?", (panel_id,)).fetchone()
    return dict(row) if row else None


def delete_panel(panel_id: int, username: str) -> bool:
    with closing(_connect()) as conn, conn:
        ok = (
            conn.execute(
                "DELETE FROM panels WHERE id = ? AND username = ? COLLATE NOCASE", (panel_id, username)
            ).rowcount
            > 0
        )
        if ok:
            conn.execute("UPDATE checks SET panel_id = NULL WHERE panel_id = ?", (panel_id,))
        return ok


def _trend(history: list[dict]) -> dict:
    """`history` — vaqt bo'yicha o'sib borish tartibida. O'zgarish: quvvat yo'qotish foizida."""
    if not history:
        return {"state": "none", "delta": None, "delta_30d": None}
    last = history[-1]
    if len(history) == 1:
        return {"state": "new", "delta": None, "delta_30d": None}

    def state_for(delta):
        if delta >= 5:
            return "worse"
        if delta <= -5:
            return "better"
        return "same"

    delta = round(last["power_loss"] - history[-2]["power_loss"], 1)

    # ~30 kun oldingi holat bilan solishtirish (agar shunday eski tekshiruv bo'lsa)
    delta_30d = None
    try:
        cutoff = datetime.strptime(last["created_at"], "%Y-%m-%d %H:%M:%S") - timedelta(days=30)
        older = [h for h in history[:-1]
                 if datetime.strptime(h["created_at"], "%Y-%m-%d %H:%M:%S") <= cutoff]
        if older:
            delta_30d = round(last["power_loss"] - older[-1]["power_loss"], 1)
    except ValueError:
        pass
    return {"state": state_for(delta), "delta": delta, "delta_30d": delta_30d}


def panel_history(panel_id: int) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, created_at, predicted_class, is_clean, power_loss, confidence, mode, hot_area"
            " FROM checks WHERE panel_id = ? ORDER BY created_at ASC, id ASC",
            (panel_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_panels(username: str) -> list[dict]:
    with closing(_connect()) as conn:
        panels = [dict(r) for r in conn.execute(
            "SELECT * FROM panels WHERE username = ? COLLATE NOCASE ORDER BY id DESC", (username,)
        ).fetchall()]
    for p in panels:
        history = panel_history(p["id"])
        p["checks"] = len(history)
        p["last"] = history[-1] if history else None
        p["trend"] = _trend(history)
        p["spark"] = [h["power_loss"] for h in history[-12:]]
    return panels


# ---------------------------------------------------------------------------
# Xarita nuqtalari (rasm EXIF GPS'i yoki panel koordinatasi)
# ---------------------------------------------------------------------------
def map_points(username=None) -> list[dict]:
    where, args = "lat IS NOT NULL AND lon IS NOT NULL", []
    if username is not None:
        where += " AND username = ? COLLATE NOCASE"
        args.append(username)
    with closing(_connect()) as conn:
        checks = [dict(r) for r in conn.execute(
            "SELECT id, created_at, filename, predicted_class, is_clean, power_loss, lat, lon, panel_id, mode"
            f" FROM checks WHERE {where} ORDER BY id DESC LIMIT 1000", args
        ).fetchall()]
        pw, pargs = "lat IS NOT NULL AND lon IS NOT NULL", []
        if username is not None:
            pw += " AND username = ? COLLATE NOCASE"
            pargs.append(username)
        panels = [dict(r) for r in conn.execute(
            f"SELECT id, name, lat, lon FROM panels WHERE {pw}", pargs
        ).fetchall()]
    return {"checks": checks, "panels": panels}
