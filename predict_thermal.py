"""
predict_thermal.py — infraqizil (termal) tasvirlar uchun inference.

Model Colab daftarida (colab/thermal_model.ipynb) o'qitiladi va `model/thermal_model.pt`
sifatida saqlanadi. Fayl bo'lmasa, ilova ishlayveradi — termal rejim "mavjud emas" deb ko'rsatiladi.

Ikki xil "issiq joy" qaytariladi (ularni aralashtirmang):
  * Grad-CAM  — model qaror qilganda tasvirning qaysi qismiga tayanganini;
  * issiq hudud maskasi — tasvirning o'zida o'rtachadan sezilarli yorqinroq joylar (nisbiy, °C emas).
"""
import base64
import io
import os

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from scipy import ndimage
from torchvision import transforms
from torchvision.models import efficientnet_b0, mobilenet_v3_large
from torchvision.transforms import InterpolationMode

import config
import predict

_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_bundle = None


def is_available() -> bool:
    return os.path.isfile(config.THERMAL_MODEL_PATH)


def _build_model(backbone: str, num_classes: int):
    if backbone == "efficientnet_b0":
        model = efficientnet_b0(weights=None)
    elif backbone == "mobilenet_v3_large":
        model = mobilenet_v3_large(weights=None)
    else:
        raise ValueError(f"Noma'lum backbone: {backbone}")
    model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, num_classes)
    return model


class _GradCAM:
    """Oxirgi konvolyutsiya bloki bo'yicha Grad-CAM (in-place amallarga chidamli)."""

    def __init__(self, model, layer):
        self.model, self.act, self.grad = model, None, None
        layer.register_forward_hook(self._forward_hook)

    def _forward_hook(self, module, inputs, output):
        self.act = output
        output.register_hook(lambda g: setattr(self, "grad", g))

    def __call__(self, x):
        self.model.eval()
        self.model.zero_grad(set_to_none=True)
        logits = self.model(x)
        idx = int(logits.argmax(1))
        logits[0, idx].backward()
        weights = self.grad.mean(dim=(2, 3), keepdim=True)
        cam = F.relu((weights * self.act).sum(1, keepdim=True))
        cam = F.interpolate(cam, size=x.shape[-2:], mode="bilinear", align_corners=False)[0, 0]
        cam = cam.detach()
        cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
        return cam.cpu().numpy(), logits.detach()


class _Bundle:
    pass


def load() -> _Bundle:
    global _bundle
    if _bundle is not None:
        return _bundle
    if not is_available():
        raise FileNotFoundError("Termal model topilmadi: " + config.THERMAL_MODEL_PATH)

    ckpt = torch.load(config.THERMAL_MODEL_PATH, map_location=_DEVICE, weights_only=False)
    class_names = ckpt["class_names"]
    model = _build_model(ckpt["backbone"], len(class_names))
    model.load_state_dict(ckpt["state_dict"])
    model.to(_DEVICE).eval()

    h, w = ckpt["img_size"]
    b = _Bundle()
    b.model, b.class_names = model, class_names
    b.normal_class = ckpt.get("normal_class", "No-Anomaly")
    b.transform = transforms.Compose([
        transforms.Resize((h, w), interpolation=InterpolationMode.BICUBIC),
        transforms.Lambda(lambda im: im.convert("RGB")),
        transforms.ToTensor(),
        transforms.Normalize(ckpt["mean"], ckpt["std"]),
    ])
    b.gradcam = _GradCAM(model, model.features[-1])
    _bundle = b
    return b


def get_class_names() -> list:
    return load().class_names


def hot_region_mask(gray_u8: np.ndarray, k: float = 1.5) -> np.ndarray:
    """Tasvir ichida o'rtachadan k*sigma yuqori yorqinlikdagi hudud (nisbiy issiq joy)."""
    g = ndimage.gaussian_filter(gray_u8.astype(np.float32), sigma=0.6)
    mask = g > (g.mean() + k * g.std())
    return ndimage.binary_opening(mask, structure=np.ones((2, 2)))


def _mask_rgba(mask: np.ndarray, size) -> Image.Image:
    """Issiq hudud maskasi: yarim shaffof qizil to'ldirish + yorqin qizil kontur."""
    inside = Image.fromarray((mask * 255).astype(np.uint8)).resize(size, Image.NEAREST)
    arr = np.asarray(inside) > 127
    edge = arr & ~ndimage.binary_erosion(arr, iterations=2)
    rgba = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    rgba[arr] = (255, 40, 40, 70)
    rgba[edge] = (255, 40, 40, 255)
    return Image.fromarray(rgba, "RGBA")


def analyze_image(pil_image: Image.Image) -> dict:
    b = load()
    gray = pil_image.convert("L")
    gray_np = np.asarray(gray)

    x = b.transform(gray).unsqueeze(0).to(_DEVICE)
    cam, logits = b.gradcam(x)
    probs = F.softmax(logits.float(), dim=1)[0].cpu().numpy()
    idx = int(probs.argmax())

    mask = hot_region_mask(gray_np)
    # Grad-CAM bu yerda butun tasvirni qoplaydi (qirqimsiz), shuning uchun to'g'ridan-to'g'ri ishlatiladi
    cam_full = np.asarray(
        Image.fromarray((cam * 255).astype(np.uint8)).resize(gray.size, Image.BILINEAR)
    ).astype(np.float32) / 255.0
    heat = predict.heatmap_rgba(cam_full)

    # "Issiqlik" ko'rinishi: kulrang tasvirni inferno-uslubidagi rangga aylantirish uchun asl rasmni qaytaramiz
    rgb = predict.to_rgb(gray)
    mask_img = _mask_rgba(mask, gray.size)
    base = rgb.convert("RGBA")
    return {
        "predicted_class": b.class_names[idx],
        "confidence": float(probs[idx]),
        "probabilities": {b.class_names[i]: float(probs[i]) for i in range(len(b.class_names))},
        "gradcam_base64": predict.to_base64_jpeg(predict.overlay_heatmap(rgb, heat)),
        "heatmap_base64": predict._to_base64_png(heat),
        "hot_mask_base64": predict._to_base64_png(mask_img),
        "hot_mask_overlay_base64": predict.to_base64_jpeg(Image.alpha_composite(base, mask_img).convert("RGB")),
        "hot_area_percent": float(mask.mean() * 100),
    }
