"""
imagetools.py — yuklangan rasmlar bilan ishlash yordamchilari:
EXIF GPS, sifat tekshiruvi (qorong'i / yorqin / xira / past ruxsat), kichik nusxa,
rasmni tahlilga tayyorlash va ZIP arxivni xavfsiz ochish.
"""
import io
import os
import zipfile

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

import config
import predict

_GPS_IFD = 0x8825


# ---------------------------------------------------------------------------
# EXIF GPS
# ---------------------------------------------------------------------------
def _dms_to_deg(dms) -> float:
    d, m, s = (float(x) for x in dms)
    return d + m / 60.0 + s / 3600.0


def extract_gps(image: Image.Image):
    """Rasm EXIF'idan (lat, lon) ni qaytaradi; bo'lmasa None."""
    try:
        gps = image.getexif().get_ifd(_GPS_IFD)
        if not gps or 2 not in gps or 4 not in gps:
            return None
        lat = _dms_to_deg(gps[2])
        lon = _dms_to_deg(gps[4])
        if str(gps.get(1, "N")).upper().startswith("S"):
            lat = -lat
        if str(gps.get(3, "E")).upper().startswith("W"):
            lon = -lon
    except Exception:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return round(lat, 6), round(lon, 6)


# ---------------------------------------------------------------------------
# Rasm sifati
# ---------------------------------------------------------------------------
def assess_quality(image: Image.Image, original_size) -> list[str]:
    """Ogohlantirish kalitlari ro'yxati: dark, bright, blurry, small."""
    gray = image.convert("L")
    gray.thumbnail((256, 256))
    arr = np.asarray(gray).astype(np.float32)

    flags = []
    mean = float(arr.mean())
    if mean < config.DARK_THRESHOLD:
        flags.append("dark")
    elif mean > config.BRIGHT_THRESHOLD:
        flags.append("bright")
    if float(ndimage.laplace(arr).var()) < config.BLUR_THRESHOLD:
        flags.append("blurry")
    if min(original_size) < config.MIN_SIDE_PX:
        flags.append("small")
    return flags


# ---------------------------------------------------------------------------
# Tayyorlash / kichik nusxa
# ---------------------------------------------------------------------------
def prepare_image(content: bytes):
    """Baytlardan tahlilga tayyor rasm tayyorlaydi.

    Qaytaradi: (rgb_rasm [katta tomoni <= MAX_IMAGE_SIDE], gps yoki None, asl_o'lcham).
    Xato bo'lsa ValueError.
    """
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Exception as exc:  # UnidentifiedImageError, OSError, DecompressionBombError ...
        raise ValueError("bad_image") from exc

    gps = extract_gps(image)               # transpose'dan oldin (EXIF yo'qolmasligi uchun)
    original_size = image.size
    image = ImageOps.exif_transpose(image)  # telefon rasmlari yon tomonga burilgan bo'lishi mumkin
    image = predict.to_rgb(image)
    image.thumbnail((config.MAX_IMAGE_SIDE, config.MAX_IMAGE_SIDE), Image.LANCZOS)
    return image, gps, original_size


def make_thumb(image: Image.Image) -> bytes:
    thumb = ImageOps.fit(image.convert("RGB"), (config.THUMB_SIDE, config.THUMB_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# ZIP
# ---------------------------------------------------------------------------
class ZipTooBig(Exception):
    pass


def expand_zip(data: bytes):
    """ZIP ichidagi rasmlarni xavfsiz ochadi.

    Qaytaradi: [(nom, baytlar yoki None, xato_kodi yoki None), ...]
    Himoya: yozuvlar soni, jami hajm va bitta fayl hajmi cheklangan (zip-bomba).
    """
    out, total = [], 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return [("archive.zip", None, "bad_zip")]

    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            base = os.path.basename(name)
            if not base or base.startswith(".") or name.startswith("__MACOSX"):
                continue
            if os.path.splitext(base)[1].lower() not in config.ALLOWED_EXTENSIONS:
                continue
            if len(out) >= config.MAX_ZIP_ENTRIES:
                out.append(("...", None, "zip_truncated"))
                break
            try:
                with zf.open(info) as fh:
                    content = fh.read(config.MAX_UPLOAD_BYTES + 1)
            except Exception:
                out.append((base, None, "bad_image"))
                continue
            if len(content) > config.MAX_UPLOAD_BYTES:
                out.append((base, None, "too_large"))
                continue
            total += len(content)
            if total > config.MAX_ZIP_TOTAL_BYTES:
                out.append(("...", None, "zip_too_big"))
                break
            out.append((base, content, None))
    return out
