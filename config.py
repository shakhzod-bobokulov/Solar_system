"""
Shared configuration for the Solar Panel Dust/Fault Detector.
Used by train.py, predict.py and app.py so class metadata stays consistent
across training and inference.
"""
import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "model")
PLOTS_DIR = os.path.join(MODEL_DIR, "plots")
MODEL_PATH = os.path.join(MODEL_DIR, "model.pt")
CLASS_NAMES_PATH = os.path.join(MODEL_DIR, "class_names.json")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Image / model settings
# ---------------------------------------------------------------------------
IMG_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB per file

# ---------------------------------------------------------------------------
# Class metadata: Uzbek label, expected power-loss range (%) and whether the
# class represents a clean (healthy) panel.
#
# Keys are "normalized" class names (lower-case, spaces/underscores -> '-')
# so that whatever folder names the Kaggle dataset ships with (Clean,
# Dusty, Bird-drop, Physical-Damage, Electrical-damage, Snow-Covered, ...)
# still map correctly regardless of exact casing/spelling.
# ---------------------------------------------------------------------------
CLASS_INFO = {
    "clean": {
        "uz": "Toza",
        "loss_range": (0, 2),
        "is_clean": True,
        "category": "clean",
    },
    "dusty": {
        "uz": "Changlangan",
        "loss_range": (15, 25),
        "is_clean": False,
        "category": "soiling",
    },
    "dust": {
        "uz": "Changlangan",
        "loss_range": (15, 25),
        "is_clean": False,
        "category": "soiling",
    },
    "bird-drop": {
        "uz": "Qush go'ng'i bilan ifloslangan",
        "loss_range": (10, 20),
        "is_clean": False,
        "category": "soiling",
    },
    "bird-droppings": {
        "uz": "Qush go'ng'i bilan ifloslangan",
        "loss_range": (10, 20),
        "is_clean": False,
        "category": "soiling",
    },
    "physical-damage": {
        "uz": "Jismoniy shikastlangan",
        "loss_range": (20, 40),
        "is_clean": False,
        "category": "damage",
    },
    "electrical-damage": {
        "uz": "Elektr zanjiri shikastlangan",
        "loss_range": (25, 50),
        "is_clean": False,
        "category": "damage",
    },
    "snow-covered": {
        "uz": "Qor bosgan",
        "loss_range": (30, 60),
        "is_clean": False,
        "category": "weather",
    },
}

# Har bir toifa uchun tavsiya etilgan chora va mos badge rangi.
CATEGORY_ACTIONS = {
    "soiling": "tozalash tavsiya etiladi",
    "weather": "qordan tozalash tavsiya etiladi",
    "damage": "texnik xizmat ko'rsatuvga murojaat qiling",
}

CATEGORY_BADGES = {
    "clean": "clean",
    "soiling": "dirty",
    "weather": "snow",
    "damage": "damage",
}

DEFAULT_CLASS_INFO = {
    "uz": None,  # filled in dynamically with the raw class name
    "loss_range": (10, 30),
    "is_clean": False,
    "category": "damage",
}


def normalize_class_key(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("_", "-")


def get_class_info(class_name: str) -> dict:
    key = normalize_class_key(class_name)
    if key in CLASS_INFO:
        return CLASS_INFO[key]
    info = dict(DEFAULT_CLASS_INFO)
    info["uz"] = class_name
    return info


# ---------------------------------------------------------------------------
# Termal (infraqizil) model — Colab daftarida o'qitiladi (colab/thermal_model.ipynb)
# ---------------------------------------------------------------------------
THERMAL_MODEL_PATH = os.environ.get(
    "THERMAL_MODEL_PATH", os.path.join(MODEL_DIR, "thermal_model.pt")
)

# Quvvat yo'qotish diapazonlari — o'lchov EMAS, muhandislik mantiqiga asoslangan taxminiy baho
# (masalan: faollashgan bypass diod odatda modulning ~1/3 qismini o'chiradi).
THERMAL_CLASS_INFO = {
    "no-anomaly":     {"loss_range": (0, 1),    "is_clean": True,  "category": "clean"},
    "cell":           {"loss_range": (2, 8),    "is_clean": False, "category": "hotspot"},
    "cell-multi":     {"loss_range": (6, 15),   "is_clean": False, "category": "hotspot"},
    "hot-spot":       {"loss_range": (2, 8),    "is_clean": False, "category": "hotspot"},
    "hot-spot-multi": {"loss_range": (6, 15),   "is_clean": False, "category": "hotspot"},
    "cracking":       {"loss_range": (3, 12),   "is_clean": False, "category": "damage"},
    "diode":          {"loss_range": (25, 35),  "is_clean": False, "category": "electrical"},
    "diode-multi":    {"loss_range": (50, 70),  "is_clean": False, "category": "electrical"},
    "offline-module": {"loss_range": (90, 100), "is_clean": False, "category": "electrical"},
    "shadowing":      {"loss_range": (10, 30),  "is_clean": False, "category": "obstruction"},
    "vegetation":     {"loss_range": (10, 40),  "is_clean": False, "category": "obstruction"},
    "soiling":        {"loss_range": (5, 20),   "is_clean": False, "category": "soiling"},
}


def get_thermal_info(class_name: str) -> dict:
    return THERMAL_CLASS_INFO.get(
        normalize_class_key(class_name),
        {"loss_range": (10, 30), "is_clean": False, "category": "damage"},
    )


# ---------------------------------------------------------------------------
# Yuklash chegaralari va sifat tekshiruvi
# ---------------------------------------------------------------------------
MAX_FILES_PER_REQUEST = 20
MAX_ZIP_ENTRIES = 60
MAX_ZIP_TOTAL_BYTES = 200 * 1024 * 1024   # arxiv ichidagi fayllarning umumiy hajmi
MAX_IMAGE_SIDE = 1280                      # tahlil/ko'rsatish uchun rasm shu o'lchamgacha kichraytiriladi
THUMB_SIDE = 96

LOW_CONFIDENCE = 0.60                      # undan past ishonchda "natija aniq emas" ogohlantirishi
BLUR_THRESHOLD = 100.0                     # Laplasian dispersiyasi (256 px da); dataset: o'tkir >=284, xira <=4
DARK_THRESHOLD = 45                        # o'rtacha yorqinlik (0..255)
BRIGHT_THRESHOLD = 220
MIN_SIDE_PX = 200                          # undan kichik rasm "past ruxsat"

# ---------------------------------------------------------------------------
# Training defaults
# ---------------------------------------------------------------------------
DEFAULT_EPOCHS = 25
DEFAULT_BATCH_SIZE = 32
DEFAULT_LR = 1e-3
DEFAULT_PATIENCE = 5  # early stopping patience (epochs without val-loss improvement)
VAL_SPLIT = 0.2
RANDOM_SEED = 42
