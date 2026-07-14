"""
Fine-tune VGG16 end-to-end for road damage classification.

This REPLACES the frozen-features + SVM approach in train_model.py, which
plateaued around 0.51 accuracy and couldn't reliably separate
longitudinal_crack from transverse_crack (a hand-crafted orientation
feature didn't fix it either -- see project notes). The hope is that a
model that actually learns from your images, instead of relying on generic
frozen ImageNet features, can pick up contextual cues a hand-crafted
feature can't.

Reuses the (already bug-fixed) labeling/sampling logic from train_model.py
so there's a single source of truth for how images get labeled.

IMPORTANT -- this runs on CPU and will be slow. Recommended workflow:

1. Smoke test first (a few minutes) to confirm everything works:
   python finetune_vgg16.py --smoke-test

2. Then kick off the real run. Expect roughly 10-30+ minutes PER EPOCH
   depending on your machine, so a 6-8 epoch run could take a few hours.
   A checkpoint is saved after every epoch (not just at the end), so you
   can stop anytime (Ctrl+C) and still have the best-so-far model saved:
   python finetune_vgg16.py --epochs 8
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader
from torchvision import models, transforms
from tqdm import tqdm

from train_model import (
    CLASS_NAMES,
    IMG_SIZE,
    MODEL_DIR,
    SEED,
    VAL_SPLIT,
    RoadDamageDataset,
    build_samples,
)

CHECKPOINT_PATH = MODEL_DIR / "road_damage_vgg16_finetuned.pt"
METADATA_PATH = MODEL_DIR / "model_metadata.json"

# Index into vgg16().features where the last conv block (block 5) starts.
# Layers before this stay frozen (generic ImageNet features); layers from
# here onward get fine-tuned on your road images.
UNFREEZE_FROM = 24


class VGG16Finetuner(nn.Module):
    def __init__(self, num_classes: int, unfreeze_from: int = UNFREEZE_FROM) -> None:
        super().__init__()
        backbone = models.vgg16(weights=models.VGG16_Weights.DEFAULT)
        self.features = backbone.features
        self.avgpool = backbone.avgpool
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(512 * 7 * 7, 512),
            nn.ReLU(inplace=True),
            nn.Dropout(0.7),
            nn.Linear(512, num_classes),
        )

        for p in self.features.parameters():
            p.requires_grad_(False)
        for layer in self.features[unfreeze_from:]:
            for p in layer.parameters():
                p.requires_grad_(True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.avgpool(x)
        return self.classifier(x)


def train_one_epoch(model, loader, optimizer, criterion, device) -> tuple[float, float]:
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    for images, labels in tqdm(loader, desc="train", leave=False):
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * images.size(0)
        correct += (outputs.argmax(1) == labels).sum().item()
        total += images.size(0)
    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(model, loader, criterion, device) -> tuple[float, float, list[int], list[int]]:
    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    all_preds: list[int] = []
    all_labels: list[int] = []
    for images, labels in tqdm(loader, desc="val", leave=False):
        images, labels = images.to(device), labels.to(device)
        outputs = model(images)
        loss = criterion(outputs, labels)
        total_loss += loss.item() * images.size(0)
        preds = outputs.argmax(1)
        correct += (preds == labels).sum().item()
        total += images.size(0)
        all_preds.extend(preds.cpu().tolist())
        all_labels.extend(labels.cpu().tolist())
    return total_loss / total, correct / total, all_preds, all_labels


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune VGG16 for road damage classification")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=16, help="Smaller batches are gentler on CPU RAM/time per step")
    parser.add_argument("--head-lr", type=float, default=1e-3, help="LR for the new classifier head")
    parser.add_argument("--backbone-lr", type=float, default=1e-5, help="LR for the unfrozen VGG16 conv layers (kept low to avoid wrecking pretrained weights)")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="L2 regularization strength -- raise this if train_acc >> val_acc (overfitting)")
    parser.add_argument("--unfreeze-from", type=int, default=UNFREEZE_FROM)
    parser.add_argument("--max-samples", type=int, default=6000)
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=1400,
        help="Cap per class before balancing. Your dataset has ~31k+ labeled images total -- "
             "raising this (e.g. 3000-4000) uses more of that pool, which helps overfitting "
             "more than tweaking epochs does.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Quick end-to-end check: tiny sample, 1 epoch. Run this before committing to a long run.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue training from the saved checkpoint instead of starting over. "
             "--epochs is the number of ADDITIONAL epochs to run, not a new total.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.smoke_test:
        args.max_samples = 200
        args.epochs = 1
        print("SMOKE TEST MODE: 200 samples, 1 epoch. This should finish in a few minutes.\n")

    torch.manual_seed(SEED)
    np.random.seed(SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    import train_model
    train_model.MAX_SAMPLES = args.max_samples
    train_model.MAX_PER_CLASS = args.max_per_class
    samples = build_samples()
    if len(samples) < 50:
        raise RuntimeError("Too few training samples. Check extraction / labeling.")

    labels = [s.label for s in samples]
    train_items, val_items = train_test_split(
        samples, test_size=VAL_SPLIT, random_state=SEED, stratify=labels
    )

    # Same augmentation policy as train_model.py: horizontal flip + mild
    # color jitter only. No rotation/vertical flip -- those would swap the
    # visual meaning of longitudinal vs. transverse cracks.
    train_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.ColorJitter(brightness=0.15, contrast=0.15),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    train_loader = DataLoader(
        RoadDamageDataset(train_items, train_tf), batch_size=args.batch_size, shuffle=True, num_workers=0
    )
    val_loader = DataLoader(
        RoadDamageDataset(val_items, val_tf), batch_size=args.batch_size, shuffle=False, num_workers=0
    )

    model = VGG16Finetuner(len(CLASS_NAMES), unfreeze_from=args.unfreeze_from).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam([
        {"params": model.classifier.parameters(), "lr": args.head_lr},
        {"params": [p for p in model.features.parameters() if p.requires_grad], "lr": args.backbone_lr},
    ], weight_decay=args.weight_decay)

    start_epoch = 0
    best_val_acc = -1.0
    best_report = ""
    best_cm: list[list[int]] = []

    if args.resume:
        if not CHECKPOINT_PATH.exists():
            raise FileNotFoundError(
                f"--resume was passed but no checkpoint found at {CHECKPOINT_PATH}. Run without --resume first."
            )
        print(f"Resuming from {CHECKPOINT_PATH} ...")
        prior = torch.load(CHECKPOINT_PATH, map_location=device, weights_only=False)
        model.load_state_dict(prior["state_dict"])
        if "optimizer_state_dict" in prior:
            optimizer.load_state_dict(prior["optimizer_state_dict"])
        start_epoch = prior.get("epoch", 0)
        best_val_acc = prior.get("best_val_accuracy", -1.0)
        print(f"  Resumed at epoch {start_epoch}, prior best_val_accuracy={best_val_acc:.3f}")
        print(f"  Will run {args.epochs} MORE epoch(s) (epochs {start_epoch + 1}-{start_epoch + args.epochs})\n")

    print(f"Train: {len(train_items)} | Val: {len(val_items)}")
    print(f"Fine-tuning features[{args.unfreeze_from}:] + new classifier head\n")

    for offset in range(1, args.epochs + 1):
        epoch = start_epoch + offset
        start = time.time()
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc, val_preds, val_labels = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - start

        print(
            f"Epoch {epoch} (this run: {offset}/{args.epochs}) "
            f"[{elapsed:.0f}s] "
            f"train_loss={train_loss:.3f} train_acc={train_acc:.3f} "
            f"val_loss={val_loss:.3f} val_acc={val_acc:.3f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_report = classification_report(
                val_labels, val_preds, target_names=CLASS_NAMES, digits=3, zero_division=0
            )
            best_cm = confusion_matrix(val_labels, val_preds).tolist()

            artifact = {
                "model_type": "vgg16_finetuned",
                "state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "class_names": CLASS_NAMES,
                "img_size": IMG_SIZE,
                "unfreeze_from": args.unfreeze_from,
                "best_val_accuracy": round(best_val_acc, 4),
                "epoch": epoch,
            }
            torch.save(artifact, CHECKPOINT_PATH)

            metadata = {
                "model_type": "vgg16_finetuned",
                "checkpoint_filename": CHECKPOINT_PATH.name,
                "class_names": CLASS_NAMES,
                "img_size": IMG_SIZE,
                "unfreeze_from": args.unfreeze_from,
                "best_val_accuracy": round(best_val_acc, 4),
                "total_samples": len(samples),
                "epochs_run": epoch,
                "classification_report": best_report,
                "confusion_matrix": best_cm,
            }
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            print(f"  -> New best (val_acc={val_acc:.3f}). Saved checkpoint.")

    print(f"\nBest validation accuracy: {best_val_acc:.3f}")
    print(best_report)


if __name__ == "__main__":
    main()
