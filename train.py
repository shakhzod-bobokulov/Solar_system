"""
train.py — Transfer-learning trainer for the Solar Panel Dust/Fault Detector.

Loads images from a local folder (ImageFolder layout: one sub-folder per
class), trains a MobileNetV3-Large (default) or EfficientNet-B0 classifier
with data augmentation, a stratified train/val split and early stopping,
then saves:

    model/model.pt              — trained weights + metadata
    model/class_names.json      — ordered list of class names
    model/plots/training_curves.png
    model/plots/confusion_matrix.png

Usage:
    python train.py --data-dir data --epochs 25 --batch-size 32
    python train.py --backbone efficientnet_b0
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import datasets, transforms
from torchvision.models import (
    MobileNet_V3_Large_Weights,
    EfficientNet_B0_Weights,
    mobilenet_v3_large,
    efficientnet_b0,
)
from PIL import Image
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, classification_report
from sklearn.utils.class_weight import compute_class_weight
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config
from predict import to_rgb


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------
class ImageListDataset(Dataset):
    """Wraps a list of (path, label) samples with its own transform, so the
    same underlying ImageFolder can be split into train/val subsets that use
    different (augmented vs. plain) transforms."""

    def __init__(self, samples, transform):
        self.samples = samples
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        image = to_rgb(Image.open(path))
        if self.transform:
            image = self.transform(image)
        return image, label


def build_transforms(img_size: int):
    train_tf = transforms.Compose(
        [
            transforms.RandomResizedCrop(img_size, scale=(0.75, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize(config.IMAGENET_MEAN, config.IMAGENET_STD),
        ]
    )
    val_tf = transforms.Compose(
        [
            transforms.Resize(int(img_size * 1.14)),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            transforms.Normalize(config.IMAGENET_MEAN, config.IMAGENET_STD),
        ]
    )
    return train_tf, val_tf


def load_datasets(data_dir: str, img_size: int, val_split: float, seed: int):
    if not os.path.isdir(data_dir):
        sys.exit(
            f"[XATO] Ma'lumotlar papkasi topilmadi: {data_dir}\n"
            "Iltimos, README.md ko'rsatmalariga muvofiq Kaggle datasetini yuklab "
            "'data/<Sinf nomi>/*.jpg' tuzilishida joylashtiring."
        )

    base = datasets.ImageFolder(data_dir)
    if len(base.classes) < 2:
        sys.exit(
            f"[XATO] Kamida 2 ta sinf papkasi kerak, topildi: {base.classes}\n"
            f"'{data_dir}' ichida har bir sinf uchun alohida papka yarating "
            "(masalan: Clean/, Dusty/)."
        )

    labels = [s[1] for s in base.samples]
    train_idx, val_idx = train_test_split(
        range(len(base.samples)),
        test_size=val_split,
        random_state=seed,
        stratify=labels,
    )
    train_samples = [base.samples[i] for i in train_idx]
    val_samples = [base.samples[i] for i in val_idx]

    train_tf, val_tf = build_transforms(img_size)
    train_ds = ImageListDataset(train_samples, train_tf)
    val_ds = ImageListDataset(val_samples, val_tf)
    return train_ds, val_ds, base.classes, [s[1] for s in train_samples]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def build_model(backbone: str, num_classes: int):
    if backbone == "mobilenet_v3_large":
        model = mobilenet_v3_large(weights=MobileNet_V3_Large_Weights.DEFAULT)
        in_features = model.classifier[-1].in_features
        model.classifier[-1] = nn.Linear(in_features, num_classes)
    elif backbone == "efficientnet_b0":
        model = efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT)
        in_features = model.classifier[-1].in_features
        model.classifier[-1] = nn.Linear(in_features, num_classes)
    else:
        raise ValueError(f"Noma'lum backbone: {backbone}")
    return model


# ---------------------------------------------------------------------------
# Train / eval loops
# ---------------------------------------------------------------------------
def run_epoch(model, loader, criterion, optimizer, device, train: bool):
    model.train() if train else model.eval()
    total_loss, correct, total = 0.0, 0, 0

    torch.set_grad_enabled(train)
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        if train:
            optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        if train:
            loss.backward()
            optimizer.step()

        total_loss += loss.item() * images.size(0)
        preds = outputs.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += images.size(0)
    torch.set_grad_enabled(True)

    return total_loss / total, correct / total


@torch.no_grad()
def collect_predictions(model, loader, device):
    model.eval()
    all_preds, all_labels = [], []
    for images, labels in loader:
        images = images.to(device)
        outputs = model(images)
        preds = outputs.argmax(dim=1).cpu().numpy()
        all_preds.extend(preds.tolist())
        all_labels.extend(labels.numpy().tolist())
    return np.array(all_labels), np.array(all_preds)


def plot_training_curves(history, out_path):
    epochs = range(1, len(history["train_loss"]) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].plot(epochs, history["train_loss"], label="Train loss")
    axes[0].plot(epochs, history["val_loss"], label="Val loss")
    axes[0].set_title("Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(epochs, history["train_acc"], label="Train acc")
    axes[1].plot(epochs, history["val_acc"], label="Val acc")
    axes[1].set_title("Accuracy")
    axes[1].set_xlabel("Epoch")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_confusion_matrix(cm, class_names, out_path):
    fig, ax = plt.subplots(figsize=(1.4 * len(class_names) + 2, 1.2 * len(class_names) + 2))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(class_names)))
    ax.set_yticks(range(len(class_names)))
    ax.set_xticklabels(class_names, rotation=45, ha="right")
    ax.set_yticklabels(class_names)
    ax.set_xlabel("Bashorat qilingan")
    ax.set_ylabel("Haqiqiy")
    ax.set_title("Confusion Matrix")

    thresh = cm.max() / 2.0 if cm.max() > 0 else 0.5
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j,
                i,
                str(cm[i, j]),
                ha="center",
                va="center",
                color="white" if cm[i, j] > thresh else "black",
            )
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Train the solar panel condition classifier")
    parser.add_argument("--data-dir", default=config.DATA_DIR)
    parser.add_argument("--epochs", type=int, default=config.DEFAULT_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=config.DEFAULT_BATCH_SIZE)
    parser.add_argument("--lr", type=float, default=config.DEFAULT_LR)
    parser.add_argument("--patience", type=int, default=config.DEFAULT_PATIENCE)
    parser.add_argument("--img-size", type=int, default=config.IMG_SIZE)
    parser.add_argument(
        "--backbone",
        choices=["mobilenet_v3_large", "efficientnet_b0"],
        default="mobilenet_v3_large",
    )
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--val-split", type=float, default=config.VAL_SPLIT)
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] Qurilma: {device}")

    train_ds, val_ds, class_names, train_labels = load_datasets(
        args.data_dir, args.img_size, args.val_split, args.seed
    )
    print(f"[INFO] Sinflar ({len(class_names)}): {class_names}")
    print(f"[INFO] Train: {len(train_ds)} ta rasm | Val: {len(val_ds)} ta rasm")

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
    )

    class_weights = compute_class_weight(
        class_weight="balanced", classes=np.arange(len(class_names)), y=np.array(train_labels)
    )
    weight_tensor = torch.tensor(class_weights, dtype=torch.float32).to(device)
    print(f"[INFO] Sinf og'irliklari (imbalance uchun): {np.round(class_weights, 3)}")

    model = build_model(args.backbone, len(class_names)).to(device)
    criterion = nn.CrossEntropyLoss(weight=weight_tensor)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=2
    )

    history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
    best_val_loss = float("inf")
    best_state = None
    epochs_without_improvement = 0

    print("[INFO] Trening boshlandi...")
    start_time = time.time()
    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc = run_epoch(model, train_loader, criterion, optimizer, device, train=True)
        val_loss, val_acc = run_epoch(model, val_loader, criterion, optimizer, device, train=False)
        scheduler.step(val_loss)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)

        print(
            f"Epoch {epoch:03d}/{args.epochs} | "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} | "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}"
        )

        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"[INFO] Erta to'xtatish: {args.patience} epoch davomida yaxshilanish yo'q.")
                break

    elapsed = time.time() - start_time
    print(f"[INFO] Trening tugadi: {elapsed / 60:.1f} daqiqa")

    if best_state is not None:
        model.load_state_dict(best_state)

    # Final evaluation with the best weights
    y_true, y_pred = collect_predictions(model, val_loader, device)
    final_val_acc = (y_true == y_pred).mean()
    print(f"\n[NATIJA] Eng yaxshi validatsiya aniqligi: {final_val_acc * 100:.2f}%\n")
    print(classification_report(y_true, y_pred, target_names=class_names, zero_division=0))

    cm = confusion_matrix(y_true, y_pred)
    plot_confusion_matrix(cm, class_names, os.path.join(config.PLOTS_DIR, "confusion_matrix.png"))
    plot_training_curves(history, os.path.join(config.PLOTS_DIR, "training_curves.png"))
    print(f"[INFO] Grafiklar saqlandi: {config.PLOTS_DIR}")

    torch.save(
        {
            "state_dict": model.state_dict(),
            "backbone": args.backbone,
            "num_classes": len(class_names),
            "img_size": args.img_size,
            "class_names": class_names,
            "val_accuracy": float(final_val_acc),
        },
        config.MODEL_PATH,
    )
    with open(config.CLASS_NAMES_PATH, "w", encoding="utf-8") as f:
        json.dump(class_names, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Model saqlandi: {config.MODEL_PATH}")
    print(f"[INFO] Sinf nomlari saqlandi: {config.CLASS_NAMES_PATH}")
    print("[INFO] Endi 'uvicorn app:app --reload' orqali web-serverni ishga tushirishingiz mumkin.")


if __name__ == "__main__":
    main()
