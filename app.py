"""
app.py — FastAPI web application for the Solar Panel Dust/Fault Detector.

Run with:
    uvicorn app:app --reload

If no trained model exists yet (model/model.pt missing), the server still
starts and the UI shows clear instructions on how to train one.
"""
import base64
import io
import os
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, UnidentifiedImageError

import config
import predict

app = FastAPI(title="Quyosh Paneli Nosozliklarini Aniqlash Tizimi")

app.mount("/static", StaticFiles(directory=os.path.join(config.BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(config.BASE_DIR, "templates"))


def build_verdict(class_name: str, confidence: float) -> dict:
    info = config.get_class_info(class_name)
    is_clean = info["is_clean"]
    category = info.get("category", "damage")
    loss_min, loss_max = info["loss_range"]
    power_loss = round(loss_min + (loss_max - loss_min) * confidence, 1)

    if is_clean:
        severity_level = "Past"
        verdict = "TOZA"
        badge = "clean"
    else:
        if confidence >= 0.75:
            severity_level = "Yuqori"
        elif confidence >= 0.45:
            severity_level = "O'rta"
        else:
            severity_level = "Past"
        action = config.CATEGORY_ACTIONS.get(category, "tekshiruvdan o'tkazish tavsiya etiladi")
        verdict = f"{info['uz'].upper()} — {action}"
        badge = config.CATEGORY_BADGES.get(category, "dirty")

    return {
        "uz_class_name": info["uz"],
        "is_clean": is_clean,
        "verdict": verdict,
        "severity_level": severity_level,
        "power_loss_percent": power_loss,
        "badge": badge,
    }


@app.get("/")
async def index(request: Request):
    model_available = predict.is_model_available()
    class_names = []
    if model_available:
        try:
            class_names = predict.get_class_names()
        except Exception:
            model_available = False
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "model_available": model_available,
            "class_names": class_names,
            "data_dir": config.DATA_DIR,
        },
    )


@app.get("/api/status")
async def status():
    model_available = predict.is_model_available()
    class_names = []
    if model_available:
        try:
            class_names = predict.get_class_names()
        except Exception:
            model_available = False
    return {"model_available": model_available, "class_names": class_names}


@app.post("/api/predict")
async def api_predict(files: list[UploadFile] = File(...)):
    if not predict.is_model_available():
        return JSONResponse(
            {
                "model_available": False,
                "message": (
                    "Trenirovka qilingan model topilmadi. Avval 'python train.py' "
                    "buyrug'ini ishga tushiring (README.md ga qarang)."
                ),
                "results": [],
            }
        )

    results = []
    for upload in files:
        filename = upload.filename or "noma'lum-fayl"
        entry = {"filename": filename}
        try:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in config.ALLOWED_EXTENSIONS:
                shown_ext = ext if ext else "noma'lum"
                allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
                raise ValueError(
                    f"Qo'llab-quvvatlanmaydigan fayl turi ({shown_ext}). "
                    f"Ruxsat etilgan: {allowed}"
                )

            content = await upload.read()
            if len(content) == 0:
                raise ValueError("Fayl bo'sh.")
            if len(content) > config.MAX_UPLOAD_BYTES:
                raise ValueError(
                    f"Fayl hajmi juda katta (max {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."
                )

            try:
                image = Image.open(io.BytesIO(content))
                image.load()
            except (UnidentifiedImageError, OSError):
                raise ValueError("Fayl yaroqsiz yoki buzilgan rasm.")

            preview_b64 = "data:image/png;base64," + base64.b64encode(
                _as_png_bytes(image)
            ).decode("ascii")

            result = predict.analyze_image(image)
            verdict = build_verdict(result["predicted_class"], result["confidence"])

            entry.update(
                {
                    "success": True,
                    "predicted_class": result["predicted_class"],
                    "confidence": result["confidence"],
                    "probabilities": result["probabilities"],
                    "gradcam_base64": result["gradcam_base64"],
                    "preview_base64": preview_b64,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    **verdict,
                }
            )
        except ValueError as exc:
            entry.update({"success": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - unexpected failure safeguard
            entry.update({"success": False, "error": f"Kutilmagan xato: {exc}"})

        results.append(entry)

    return {"model_available": True, "results": results}


def _as_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    predict.to_rgb(image).save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
