"""
predict.py — Single-image inference + Grad-CAM for the Solar Panel
Dust/Fault Detector.

Exposes:
    is_model_available() -> bool
    get_class_names()    -> list[str]
    analyze_image(pil_image) -> dict with prediction, probabilities and a
                                 base64 Grad-CAM heatmap overlay.

Can also be run directly for a quick CLI check:
    python predict.py path/to/image.jpg
"""
import base64
import io
import json
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.models import mobilenet_v3_large, efficientnet_b0

import config

_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Module-level cache so the model is loaded once per process.
_bundle = None


def to_rgb(image: Image.Image) -> Image.Image:
    """Safely converts any PIL image to RGB.

    Palette images ("P" mode) that carry transparency as raw bytes must be
    expanded to RGBA first - converting them straight to RGB makes Pillow
    emit a "Palette images with Transparency..." UserWarning.
    """
    if image.mode == "P" and "transparency" in image.info:
        image = image.convert("RGBA")
    if image.mode in ("RGBA", "LA"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.convert("RGBA").split()[-1])
        return background
    return image.convert("RGB")


class _GradCAM:
    """Minimal Grad-CAM hook wrapper around a model's last conv block."""

    def __init__(self, model, target_layer):
        self.model = model
        self.activations = None
        self.gradients = None
        target_layer.register_forward_hook(self._save_activation)
        target_layer.register_full_backward_hook(self._save_gradient)

    def _save_activation(self, module, inputs, output):
        self.activations = output

    def _save_gradient(self, module, grad_input, grad_output):
        self.gradients = grad_output[0]

    def generate(self, logits, class_idx):
        self.model.zero_grad(set_to_none=True)
        score = logits[0, class_idx]
        score.backward(retain_graph=True)

        gradients = self.gradients[0]          # (C, H, W)
        activations = self.activations[0]      # (C, H, W)
        weights = gradients.mean(dim=(1, 2))   # (C,)
        cam = torch.relu((weights[:, None, None] * activations).sum(dim=0))
        cam = cam.detach()
        cam -= cam.min()
        if cam.max() > 1e-8:
            cam /= cam.max()
        return cam.cpu().numpy()


class ModelBundle:
    def __init__(self, model, class_names, img_size):
        self.model = model
        self.class_names = class_names
        self.img_size = img_size
        self.transform = transforms.Compose(
            [
                transforms.Resize(int(img_size * 1.14)),
                transforms.CenterCrop(img_size),
                transforms.ToTensor(),
                transforms.Normalize(config.IMAGENET_MEAN, config.IMAGENET_STD),
            ]
        )
        target_layer = model.features[-1]
        self.gradcam = _GradCAM(model, target_layer)


def is_model_available() -> bool:
    return os.path.isfile(config.MODEL_PATH) and os.path.isfile(config.CLASS_NAMES_PATH)


def _build_model(backbone: str, num_classes: int):
    if backbone == "mobilenet_v3_large":
        model = mobilenet_v3_large(weights=None)
        in_features = model.classifier[-1].in_features
        model.classifier[-1] = torch.nn.Linear(in_features, num_classes)
    elif backbone == "efficientnet_b0":
        model = efficientnet_b0(weights=None)
        in_features = model.classifier[-1].in_features
        model.classifier[-1] = torch.nn.Linear(in_features, num_classes)
    else:
        raise ValueError(f"Noma'lum backbone: {backbone}")
    return model


def load_model() -> ModelBundle:
    global _bundle
    if _bundle is not None:
        return _bundle

    if not is_model_available():
        raise FileNotFoundError(
            "Trenirovka qilingan model topilmadi. Avval 'python train.py' ni ishga tushiring."
        )

    checkpoint = torch.load(config.MODEL_PATH, map_location=_DEVICE)
    class_names = checkpoint.get("class_names")
    if class_names is None:
        with open(config.CLASS_NAMES_PATH, "r", encoding="utf-8") as f:
            class_names = json.load(f)

    model = _build_model(checkpoint["backbone"], checkpoint["num_classes"])
    model.load_state_dict(checkpoint["state_dict"])
    model.to(_DEVICE)
    model.eval()

    img_size = checkpoint.get("img_size", config.IMG_SIZE)
    _bundle = ModelBundle(model, class_names, img_size)
    return _bundle


def get_class_names() -> list:
    return load_model().class_names


def _colorize_cam(cam: np.ndarray, size) -> Image.Image:
    """Map a 0..1 grayscale CAM array to a jet-like RGBA heatmap image."""
    # Simple jet-style colormap without needing matplotlib at inference time.
    cam_img = Image.fromarray((cam * 255).astype(np.uint8)).resize(size, Image.BILINEAR)
    cam_arr = np.asarray(cam_img).astype(np.float32) / 255.0

    r = np.clip(1.5 - np.abs(4 * cam_arr - 3), 0, 1)
    g = np.clip(1.5 - np.abs(4 * cam_arr - 2), 0, 1)
    b = np.clip(1.5 - np.abs(4 * cam_arr - 1), 0, 1)
    heatmap = np.stack([r, g, b], axis=-1)
    return Image.fromarray((heatmap * 255).astype(np.uint8)).convert("RGB")


def _overlay_heatmap(original: Image.Image, cam: np.ndarray, alpha: float = 0.45) -> Image.Image:
    original_rgb = original.convert("RGB")
    heatmap = _colorize_cam(cam, original_rgb.size)
    blended = Image.blend(original_rgb, heatmap, alpha)
    return blended


def _to_base64_png(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def analyze_image(pil_image: Image.Image) -> dict:
    """Runs classification + Grad-CAM on a single PIL image.

    Returns a dict:
        {
          "predicted_class": str,
          "confidence": float (0..1),
          "probabilities": {class_name: prob, ...},
          "gradcam_base64": "data:image/png;base64,....",
        }
    """
    bundle = load_model()
    model = bundle.model

    image_rgb = to_rgb(pil_image)
    input_tensor = bundle.transform(image_rgb).unsqueeze(0).to(_DEVICE)
    input_tensor.requires_grad_(False)

    logits = model(input_tensor)
    probs = F.softmax(logits, dim=1)[0]
    predicted_idx = int(torch.argmax(probs).item())
    confidence = float(probs[predicted_idx].item())

    cam = bundle.gradcam.generate(logits, predicted_idx)
    overlay = _overlay_heatmap(image_rgb, cam)
    gradcam_b64 = _to_base64_png(overlay)

    probabilities = {
        bundle.class_names[i]: float(probs[i].item()) for i in range(len(bundle.class_names))
    }

    return {
        "predicted_class": bundle.class_names[predicted_idx],
        "confidence": confidence,
        "probabilities": probabilities,
        "gradcam_base64": gradcam_b64,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Foydalanish: python predict.py path/to/image.jpg")
        sys.exit(1)

    img_path = sys.argv[1]
    if not os.path.isfile(img_path):
        sys.exit(f"[XATO] Fayl topilmadi: {img_path}")

    img = Image.open(img_path)
    result = analyze_image(img)
    print(f"Bashorat: {result['predicted_class']} ({result['confidence'] * 100:.1f}%)")
    print("Barcha ehtimolliklar:")
    for cls, p in sorted(result["probabilities"].items(), key=lambda x: -x[1]):
        print(f"  {cls}: {p * 100:.2f}%")
