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
# Training defaults
# ---------------------------------------------------------------------------
DEFAULT_EPOCHS = 25
DEFAULT_BATCH_SIZE = 32
DEFAULT_LR = 1e-3
DEFAULT_PATIENCE = 5  # early stopping patience (epochs without val-loss improvement)
VAL_SPLIT = 0.2
RANDOM_SEED = 42
