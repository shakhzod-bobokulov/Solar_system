"""
app.py — FastAPI web application for the Solar Panel Dust/Fault Detector.

Run with:
    uvicorn app:app --reload

If no trained model exists yet (model/model.pt missing), the server still
starts and the UI shows clear instructions on how to train one.

Kirish: admin hisobi (ADMIN_USERNAME / ADMIN_PASSWORD muhit o'zgaruvchilari).
"""
import asyncio
import base64
import csv
import io
import os
import time
from datetime import datetime

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import threading
from starlette.middleware.sessions import SessionMiddleware

import auth
import config
import imagetools
import mailer
import predict
import predict_thermal
import store

app = FastAPI(title="Quyosh Paneli Nosozliklarini Aniqlash Tizimi")
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.load_secret_key(),
    session_cookie="solar_session",
    max_age=8 * 60 * 60,
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=os.path.join(config.BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(config.BASE_DIR, "templates"))

store.init_db()
store.init_users()
if auth.admin_password_is_default():
    print(
        "OGOHLANTIRISH: standart admin paroli ishlatilmoqda. "
        "ADMIN_PASSWORD muhit o'zgaruvchisini o'rnating."
    )


class CheckError(ValueError):
    """Foydalanuvchiga ko'rsatiladigan xato; `code` brauzerda tarjima qilinadi."""

    def __init__(self, code: str, message: str, **params):
        super().__init__(message)
        self.code = code
        self.params = params


def current_user(request: Request):
    user = request.session.get("user")
    # Bloklangan yoki o'chirilgan foydalanuvchining sessiyasi darhol bekor qilinadi
    if user and request.session.get("role") == "user" and not store.is_user_active(user):
        request.session.clear()
        return None
    return user


def is_admin(request: Request) -> bool:
    return request.session.get("role") == "admin"


def unauthorized() -> JSONResponse:
    return JSONResponse({"error": "unauthorized"}, status_code=401)


def build_verdict(class_name: str, confidence: float) -> dict:
    info = config.get_class_info(class_name)
    is_clean = info["is_clean"]
    category = info.get("category", "damage")
    loss_min, loss_max = info["loss_range"]
    power_loss = round(loss_min + (loss_max - loss_min) * confidence, 1)

    if is_clean:
        severity_level, severity_key = "Past", "low"
        verdict = "TOZA"
        badge = "clean"
    else:
        if confidence >= 0.75:
            severity_level, severity_key = "Yuqori", "high"
        elif confidence >= 0.45:
            severity_level, severity_key = "O'rta", "medium"
        else:
            severity_level, severity_key = "Past", "low"
        action = config.CATEGORY_ACTIONS.get(category, "tekshiruvdan o'tkazish tavsiya etiladi")
        verdict = f"{info['uz'].upper()} — {action}"
        badge = config.CATEGORY_BADGES.get(category, "dirty")

    return {
        "uz_class_name": info["uz"],
        "is_clean": is_clean,
        "verdict": verdict,
        "severity_level": severity_level,
        "severity_key": severity_key,
        "category": category,
        "power_loss_percent": power_loss,
        "badge": badge,
    }


# ---------------------------------------------------------------------------
# Autentifikatsiya
# ---------------------------------------------------------------------------
@app.get("/login")
async def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/admin" if is_admin(request) else "/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def pick_lang(value) -> str:
    return value if value in ("uz", "ru", "en") else "uz"


async def issue_code(email: str, purpose: str, lang: str, force: bool = False) -> str:
    """Kod yaratib yuboradi. 'sent' | 'dev' | 'wait' | 'mail_failed' qaytaradi."""
    now = time.time()
    existing = store.get_code(email, purpose)
    if not force and existing and now - existing["created_at"] < auth.CODE_RESEND_COOLDOWN:
        return "wait"
    code = auth.generate_code()
    store.save_code(
        email, purpose, auth.hash_code(email, purpose, code), now + auth.CODE_TTL_SECONDS, now
    )
    try:
        return await asyncio.to_thread(mailer.send_code, email, code, purpose, lang)
    except mailer.MailError as exc:
        print(f"Email yuborishda xato: {exc}")
        return "mail_failed"


def check_code(email: str, purpose: str, code: str) -> str:
    """'ok' | 'code' (noto'g'ri) | 'expired' qaytaradi."""
    row = store.get_code(email, purpose)
    if not row or row["expires_at"] < time.time() or row["attempts"] >= auth.CODE_MAX_ATTEMPTS:
        return "expired"
    if hmac_equal(auth.hash_code(email, purpose, code), row["code_hash"]):
        store.delete_code(email, purpose)
        return "ok"
    store.bump_code_attempts(email, purpose)
    if row["attempts"] + 1 >= auth.CODE_MAX_ATTEMPTS:
        store.delete_code(email, purpose)
        return "expired"
    return "code"


def hmac_equal(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a, b)


def start_session(request: Request, username: str, role: str) -> None:
    request.session.clear()
    request.session["user"] = username
    request.session["role"] = role


async def read_json(request: Request) -> dict:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


@app.post("/api/login")
async def api_login(request: Request):
    ip = client_ip(request)
    if auth.is_locked(ip):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    identifier = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))

    if auth.check_credentials(identifier, password):
        auth.reset_failures(ip)
        start_session(request, auth.ADMIN_USERNAME, "admin")
        return {"ok": True, "role": "admin"}

    user = store.get_user_by_login(auth.normalize_email(identifier) if "@" in identifier else identifier)
    # Foydalanuvchi topilmasa ham xesh hisoblanadi (vaqt bo'yicha farq bildirmaslik uchun)
    stored = user["password_hash"] if user else auth.DUMMY_HASH
    if not (auth.verify_password(password, stored) and user):
        auth.register_failure(ip)
        return JSONResponse({"error": "invalid"}, status_code=401)

    auth.reset_failures(ip)
    if user["blocked"]:
        return JSONResponse({"error": "blocked"}, status_code=403)
    if not user["verified"]:
        return JSONResponse({"error": "unverified", "email": user["email"]}, status_code=403)
    start_session(request, user["username"], "user")
    return {"ok": True, "role": "user"}


@app.post("/api/register")
async def api_register(request: Request):
    if not auth.rate_ok("register", client_ip(request), 10, 3600):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    username = str(body.get("username", "")).strip()
    email = auth.normalize_email(str(body.get("email", "")))
    password = str(body.get("password", ""))
    lang = pick_lang(body.get("lang"))

    problem = auth.validate_registration(username, email, password)
    if problem:
        return JSONResponse({"error": problem}, status_code=400)

    store.delete_stale_unverified()
    password_hash = auth.hash_password(password)
    existing = store.get_user_by_email(email)
    if existing and existing["verified"]:
        return JSONResponse({"error": "email_exists"}, status_code=409)
    if existing:
        # Tasdiqlanmagan hisob: egasi qayta urinmoqda — ma'lumotlarini yangilaymiz
        if not store.update_unverified(email, username, password_hash):
            return JSONResponse({"error": "exists"}, status_code=409)
    elif not store.create_user(username, email, password_hash):
        return JSONResponse({"error": "exists"}, status_code=409)

    status = await issue_code(email, "verify", lang, force=True)
    if status == "mail_failed":
        return JSONResponse({"error": "mail_failed", "email": email}, status_code=502)
    return {"ok": True, "email": email, "dev": status == "dev"}


@app.post("/api/verify")
async def api_verify(request: Request):
    if not auth.rate_ok("verify", client_ip(request), 20, 600):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    email = auth.normalize_email(str(body.get("email", "")))
    code = str(body.get("code", "")).strip()
    user = store.get_user_by_email(email)
    if not user or user["verified"]:
        return JSONResponse({"error": "expired"}, status_code=400)

    result = check_code(email, "verify", code)
    if result != "ok":
        return JSONResponse({"error": result}, status_code=400)
    store.set_verified(email)
    start_session(request, user["username"], "user")
    return {"ok": True, "role": "user"}


@app.post("/api/resend")
async def api_resend(request: Request):
    if not auth.rate_ok("resend", client_ip(request), 10, 3600):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    email = auth.normalize_email(str(body.get("email", "")))
    lang = pick_lang(body.get("lang"))
    user = store.get_user_by_email(email)
    if not user or user["verified"]:
        return {"ok": True, "dev": not mailer.is_configured()}  # mavjudligini oshkor qilmaymiz
    status = await issue_code(email, "verify", lang)
    if status == "wait":
        return JSONResponse({"error": "wait"}, status_code=429)
    if status == "mail_failed":
        return JSONResponse({"error": "mail_failed"}, status_code=502)
    return {"ok": True, "dev": status == "dev"}


@app.post("/api/forgot")
async def api_forgot(request: Request):
    if not auth.rate_ok("forgot", client_ip(request), 10, 3600):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    email = auth.normalize_email(str(body.get("email", "")))
    lang = pick_lang(body.get("lang"))
    if not auth.valid_email(email):
        return JSONResponse({"error": "email"}, status_code=400)
    user = store.get_user_by_email(email)
    if user and user["verified"]:
        status = await issue_code(email, "reset", lang)
        if status == "mail_failed":
            return JSONResponse({"error": "mail_failed"}, status_code=502)
    # Hisob bor-yo'qligidan qat'i nazar bir xil javob (email mavjudligini oshkor qilmaymiz)
    return {"ok": True, "dev": not mailer.is_configured()}


@app.post("/api/reset")
async def api_reset(request: Request):
    if not auth.rate_ok("reset", client_ip(request), 20, 600):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    email = auth.normalize_email(str(body.get("email", "")))
    code = str(body.get("code", "")).strip()
    password = str(body.get("password", ""))
    if not auth.valid_password(password):
        return JSONResponse({"error": "password"}, status_code=400)
    user = store.get_user_by_email(email)
    if not user or not user["verified"]:
        return JSONResponse({"error": "expired"}, status_code=400)

    result = check_code(email, "reset", code)
    if result != "ok":
        return JSONResponse({"error": result}, status_code=400)
    store.set_password(email, auth.hash_password(password))
    return {"ok": True}


@app.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------
MODES = ("rgb", "thermal")
_infer_lock = threading.Lock()  # Grad-CAM hook'lari umumiy holatda ishlaydi — tahlil ketma-ket bajariladi

THERMAL_ACTIONS = {
    "hotspot": "qizigan joyni texnik ko'rikdan o'tkazing",
    "electrical": "elektr nosozlik: modul/diodni tekshiring",
    "obstruction": "to'siqni (soya/o'simlik) bartaraf eting",
    "damage": "texnik xizmat ko'rsatuvga murojaat qiling",
    "soiling": "tozalash tavsiya etiladi",
}


def severity_for(confidence: float, is_clean: bool):
    if is_clean:
        return "Past", "low"
    if confidence >= 0.75:
        return "Yuqori", "high"
    if confidence >= 0.45:
        return "O'rta", "medium"
    return "Past", "low"


def build_thermal_verdict(class_name: str, confidence: float) -> dict:
    info = config.get_thermal_info(class_name)
    is_clean = info["is_clean"]
    category = info["category"]
    loss_min, loss_max = info["loss_range"]
    severity_level, severity_key = severity_for(confidence, is_clean)
    action = THERMAL_ACTIONS.get(category, "tekshiruvdan o'tkazish tavsiya etiladi")
    return {
        "uz_class_name": class_name,
        "is_clean": is_clean,
        "verdict": "NORMAL" if is_clean else f"{class_name.upper()} — {action}",
        "severity_level": severity_level,
        "severity_key": severity_key,
        "category": category,
        "power_loss_percent": round(loss_min + (loss_max - loss_min) * confidence, 1),
        "badge": "clean" if is_clean else "dirty",
    }


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_coord(value, lo, hi):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("coord")
    if not (lo <= number <= hi):
        raise ValueError("coord")
    return round(number, 6)


def require_login(request: Request):
    """Foydalanuvchi nomini qaytaradi yoki None."""
    return current_user(request)


def thermal_classes() -> list:
    if not predict_thermal.is_available():
        return []
    try:
        return predict_thermal.get_class_names()
    except Exception:
        return []


def rgb_classes() -> list:
    if not predict.is_model_available():
        return []
    try:
        return predict.get_class_names()
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------
@app.get("/admin")
async def admin_page(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    if not is_admin(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "admin.html", {"user": current_user(request)})


@app.get("/api/admin/overview")
async def admin_overview(request: Request):
    if not is_admin(request):
        return unauthorized()
    return {
        "stats": store.get_stats(),
        "checks": store.list_checks(),
        "users": store.list_users(),
        "daily": store.get_daily(14),
        "monthly": store.get_monthly(12),
        "default_password": auth.admin_password_is_default(),
    }


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, request: Request):
    if not is_admin(request):
        return unauthorized()
    if not store.delete_user(user_id):
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/block")
async def admin_block_user(user_id: int, request: Request):
    if not is_admin(request):
        return unauthorized()
    body = await read_json(request)
    blocked = bool(body.get("blocked", True))
    if not store.set_blocked(user_id, blocked):
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"ok": True, "blocked": blocked}


@app.post("/api/admin/password")
async def admin_change_password(request: Request):
    if not is_admin(request):
        return unauthorized()
    if not auth.rate_ok("admin_pw", client_ip(request), 10, 600):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    current = str(body.get("current", ""))
    new = str(body.get("new", ""))
    if not auth.check_credentials(auth.ADMIN_USERNAME, current):
        return JSONResponse({"error": "wrong_current"}, status_code=400)
    if not auth.valid_password(new):
        return JSONResponse({"error": "password"}, status_code=400)
    store.set_setting(auth.ADMIN_HASH_KEY, auth.hash_password(new))
    return {"ok": True}


@app.delete("/api/admin/checks")
async def admin_clear(request: Request):
    if not is_admin(request):
        return unauthorized()
    return {"deleted": store.clear_checks()}


@app.get("/api/admin/map")
async def admin_map(request: Request):
    if not is_admin(request):
        return unauthorized()
    return store.map_points()


@app.get("/api/admin/export.csv")
async def admin_export(request: Request):
    if not is_admin(request):
        return unauthorized()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "created_at", "username", "mode", "filename", "predicted_class", "confidence",
         "severity", "power_loss_percent", "hot_area_percent", "feedback", "feedback_class",
         "lat", "lon", "panel_id"]
    )
    for r in store.list_checks(limit=100000):
        feedback = "" if r["fb_ok"] is None else ("correct" if r["fb_ok"] else "wrong")
        writer.writerow(
            [r["id"], r["created_at"], r["username"], r["mode"], r["filename"], r["predicted_class"],
             r["confidence"], r["severity_key"], r["power_loss"], r["hot_area"], feedback,
             r["fb_class"], r["lat"], r["lon"], r["panel_id"]]
        )
    # utf-8-sig: Excel kirill va lotin belgilarini to'g'ri ochishi uchun
    return Response(
        buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=checks.csv"},
    )


# ---------------------------------------------------------------------------
# Foydalanuvchi kabineti: tarix, panellar, xarita
# ---------------------------------------------------------------------------
@app.get("/account")
async def account_page(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "account.html",
        {"user": current_user(request), "is_admin": is_admin(request)},
    )


@app.get("/api/me/checks")
async def me_checks(request: Request, q: str = "", cls: str = "", panel_id: str = "", limit: int = 300):
    user = require_login(request)
    if not user:
        return unauthorized()
    rows = store.list_checks(
        limit=max(1, min(limit, 1000)),
        username=user,
        q=q.strip() or None,
        cls=cls or None,
        panel_id=parse_int(panel_id),
    )
    total = len(rows)
    clean = sum(1 for r in rows if r["is_clean"])
    avg = round(sum(r["power_loss"] for r in rows) / total, 1) if total else None
    classes = sorted({r["predicted_class"] for r in store.list_checks(limit=1000, username=user)})
    return {
        "checks": rows,
        "summary": {"total": total, "clean": clean, "faulty": total - clean, "avg_loss": avg},
        "classes": classes,
    }


@app.delete("/api/me/checks/{check_id}")
async def me_delete_check(check_id: int, request: Request):
    user = require_login(request)
    if not user:
        return unauthorized()
    if not store.delete_check(check_id, username=user):
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"ok": True}


@app.get("/api/checks/{check_id}/thumb")
async def check_thumb(check_id: int, request: Request):
    user = current_user(request)
    data = store.get_thumb(check_id)
    if not data:
        return JSONResponse({"error": "not_found"}, status_code=404)
    content, owner = data
    if not (is_admin(request) or (user and user.lower() == owner.lower())):
        return unauthorized()
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/me/map")
async def me_map(request: Request):
    user = require_login(request)
    if not user:
        return unauthorized()
    return store.map_points(username=user)


@app.get("/api/panels")
async def panels_list(request: Request):
    user = require_login(request)
    if not user:
        return unauthorized()
    return {"panels": store.list_panels(user)}


@app.post("/api/panels")
async def panels_create(request: Request):
    user = require_login(request)
    if not user:
        return unauthorized()
    if not auth.rate_ok("panel_create", user, 60, 3600):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    name = str(body.get("name", "")).strip()
    if not (1 <= len(name) <= 60):
        return JSONResponse({"error": "name"}, status_code=400)
    try:
        lat = parse_coord(body.get("lat"), -90, 90)
        lon = parse_coord(body.get("lon"), -180, 180)
    except ValueError:
        return JSONResponse({"error": "coord"}, status_code=400)
    if (lat is None) != (lon is None):
        return JSONResponse({"error": "coord"}, status_code=400)
    panel_id = store.create_panel(user, name, lat, lon)
    return {"ok": True, "id": panel_id}


@app.delete("/api/panels/{panel_id}")
async def panels_delete(panel_id: int, request: Request):
    user = require_login(request)
    if not user:
        return unauthorized()
    if not store.delete_panel(panel_id, user):
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"ok": True}


@app.get("/api/panels/{panel_id}/history")
async def panels_history(panel_id: int, request: Request):
    user = require_login(request)
    if not user:
        return unauthorized()
    panel = store.get_panel(panel_id)
    if not panel or panel["username"].lower() != user.lower():
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"panel": panel, "history": store.panel_history(panel_id)}


# ---------------------------------------------------------------------------
# PWA: service worker va manifest (service worker butun saytni qamrashi uchun ildizdan beriladi)
# ---------------------------------------------------------------------------
@app.get("/sw.js")
async def service_worker():
    return FileResponse(
        os.path.join(config.BASE_DIR, "static", "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(
        os.path.join(config.BASE_DIR, "static", "manifest.webmanifest"),
        media_type="application/manifest+json",
    )


# ---------------------------------------------------------------------------
# Asosiy ilova
# ---------------------------------------------------------------------------
def model_state():
    rgb = rgb_classes()
    return {
        "model_available": bool(rgb),
        "class_names": rgb,
        "thermal_available": predict_thermal.is_available() and bool(thermal_classes()),
        "thermal_class_names": thermal_classes(),
    }


@app.get("/")
async def index(request: Request):
    state = model_state()
    panels = store.list_panels(current_user(request)) if current_user(request) else []
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            **state,
            "data_dir": config.DATA_DIR,
            "user": current_user(request),
            "is_admin": is_admin(request),
            "panels": [{"id": p["id"], "name": p["name"]} for p in panels],
            "max_files": config.MAX_FILES_PER_REQUEST,
        },
    )


@app.get("/api/status")
async def status():
    return model_state()


def process_image(content: bytes, filename: str, mode: str, username: str, panel_id) -> dict:
    """Bitta rasmni tahlil qilib, bazaga yozadi. CPU'ni band qiladi — thread'da chaqiriladi."""
    try:
        image, gps, original_size = imagetools.prepare_image(content)
    except ValueError:
        raise CheckError("bad_image", "Fayl yaroqsiz yoki buzilgan rasm.")

    warnings = imagetools.assess_quality(image, original_size) if mode == "rgb" else []

    with _infer_lock:
        if mode == "thermal":
            result = predict_thermal.analyze_image(image)
            verdict = build_thermal_verdict(result["predicted_class"], result["confidence"])
        else:
            result = predict.analyze_image(image)
            verdict = build_verdict(result["predicted_class"], result["confidence"])

    hot_area = result.get("hot_area_percent")
    check_id = store.add_check(
        username=username,
        filename=filename,
        predicted_class=result["predicted_class"],
        category=verdict["category"],
        is_clean=verdict["is_clean"],
        confidence=result["confidence"],
        severity_key=verdict["severity_key"],
        power_loss=verdict["power_loss_percent"],
        mode=mode,
        panel_id=panel_id,
        lat=gps[0] if gps else None,
        lon=gps[1] if gps else None,
        thumb=imagetools.make_thumb(image),
        hot_area=hot_area,
    )

    entry = {
        "success": True,
        "id": check_id,
        "mode": mode,
        "predicted_class": result["predicted_class"],
        "confidence": result["confidence"],
        "low_confidence": result["confidence"] < config.LOW_CONFIDENCE,
        "quality_warnings": warnings,
        "probabilities": result["probabilities"],
        "gradcam_base64": result["gradcam_base64"],
        "heatmap_base64": result["heatmap_base64"],
        "preview_base64": predict.to_base64_jpeg(image),
        "gps": {"lat": gps[0], "lon": gps[1]} if gps else None,
        "panel_id": panel_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **verdict,
    }
    if mode == "thermal":
        entry["hot_area_percent"] = round(hot_area, 1)
        entry["hot_mask_base64"] = result["hot_mask_base64"]
        entry["hot_mask_overlay_base64"] = result["hot_mask_overlay_base64"]
    return entry


def error_entry(filename: str, source_index: int, exc: Exception) -> dict:
    entry = {"filename": filename, "source_index": source_index, "success": False}
    if isinstance(exc, CheckError):
        entry.update({"error": str(exc), "error_code": exc.code, "error_params": exc.params})
    else:
        entry["error"] = f"Kutilmagan xato: {exc}"
    return entry


@app.post("/api/predict")
async def api_predict(
    request: Request,
    files: list[UploadFile] = File(...),
    mode: str = Form("rgb"),
    panel_id: str = Form(""),
):
    if mode not in MODES:
        mode = "rgb"
    if mode == "thermal":
        ready = predict_thermal.is_available() and bool(thermal_classes())
        missing_message = "Termal model topilmadi (model/thermal_model.pt)."
    else:
        ready = predict.is_model_available()
        missing_message = (
            "Trenirovka qilingan model topilmadi. Avval 'python train.py' "
            "buyrug'ini ishga tushiring (README.md ga qarang)."
        )
    if not ready:
        return JSONResponse(
            {"model_available": False, "mode": mode, "message": missing_message, "results": []}
        )
    if len(files) > config.MAX_FILES_PER_REQUEST:
        return JSONResponse({"error": "too_many_files", "max": config.MAX_FILES_PER_REQUEST}, status_code=413)

    username = current_user(request)
    # Panelga bog'lash faqat o'z panelingiz uchun mumkin
    panel = parse_int(panel_id)
    if panel is not None:
        owned = store.get_panel(panel)
        panel = panel if (username and owned and owned["username"].lower() == username.lower()) else None

    results = []
    for index_in_request, upload in enumerate(files):
        filename = upload.filename or "noma'lum-fayl"
        ext = os.path.splitext(filename)[1].lower()
        try:
            if ext not in config.ALLOWED_EXTENSIONS and ext != ".zip":
                shown_ext = ext if ext else "noma'lum"
                allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS | {".zip"}))
                raise CheckError(
                    "bad_type",
                    f"Qo'llab-quvvatlanmaydigan fayl turi ({shown_ext}). Ruxsat etilgan: {allowed}",
                    ext=shown_ext,
                    allowed=allowed,
                )
            content = await upload.read()
            if len(content) == 0:
                raise CheckError("empty", "Fayl bo'sh.")
            if len(content) > config.MAX_ZIP_TOTAL_BYTES if ext == ".zip" else len(content) > config.MAX_UPLOAD_BYTES:
                max_mb = (config.MAX_ZIP_TOTAL_BYTES if ext == ".zip" else config.MAX_UPLOAD_BYTES) // (1024 * 1024)
                raise CheckError("too_large", f"Fayl hajmi juda katta (max {max_mb} MB).", mb=max_mb)
        except CheckError as exc:
            results.append(error_entry(filename, index_in_request, exc))
            continue

        # ZIP bo'lsa, ichidagi har bir rasm alohida tahlil qilinadi
        if ext == ".zip":
            inner = await asyncio.to_thread(imagetools.expand_zip, content)
            jobs = [(f"{filename}/{name}", data, err) for name, data, err in inner]
            if not jobs:
                results.append(error_entry(filename, index_in_request, CheckError("zip_empty", "Arxivda rasm yo'q.")))
                continue
        else:
            jobs = [(filename, content, None)]

        for name, data, err in jobs:
            if err:
                message = {"bad_zip": "ZIP fayl buzilgan.", "zip_truncated": "Arxivda juda ko'p rasm: faqat dastlabkilari tahlil qilindi.",
                           "zip_too_big": "Arxiv ichidagi fayllar hajmi juda katta.", "too_large": "Fayl hajmi juda katta.",
                           "bad_image": "Fayl yaroqsiz yoki buzilgan rasm."}.get(err, err)
                results.append(error_entry(name, index_in_request, CheckError(err, message)))
                continue
            try:
                entry = await asyncio.to_thread(process_image, data, name, mode, username or "guest", panel)
                entry["filename"] = name
                entry["source_index"] = index_in_request
                results.append(entry)
            except Exception as exc:  # noqa: BLE001 - kutilmagan xatoni foydalanuvchiga ko'rsatamiz
                results.append(error_entry(name, index_in_request, exc))

    return {"model_available": True, "mode": mode, "results": results}


@app.post("/api/feedback")
async def api_feedback(request: Request):
    if not auth.rate_ok("feedback", client_ip(request), 120, 600):
        return JSONResponse({"error": "too_many"}, status_code=429)
    body = await read_json(request)
    check_id = parse_int(body.get("check_id"))
    ok = body.get("ok")
    if check_id is None or not isinstance(ok, bool):
        return JSONResponse({"error": "invalid"}, status_code=400)

    check = store.get_check(check_id)
    if not check:
        return JSONResponse({"error": "not_found"}, status_code=404)
    me = current_user(request) or "guest"
    if not is_admin(request) and check["username"].lower() != me.lower():
        return unauthorized()

    correct_class = None
    if not ok:
        raw = str(body.get("correct_class") or "").strip()
        allowed = thermal_classes() if check["mode"] == "thermal" else rgb_classes()
        if raw:
            if raw not in allowed:
                return JSONResponse({"error": "invalid_class"}, status_code=400)
            correct_class = raw
    store.set_feedback(check_id, ok, correct_class)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
