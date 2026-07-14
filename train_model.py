"""
Train a road-damage classifier using VGG16 features and an RBF-kernel SVM.

Uses supervised labels from Pascal VOC XML annotations mapped to the
RoadWatch PH UI categories.

CHANGELOG (fixes over the original version):
1. label_from_xml: images are ONLY labeled "intact_road" if they have zero
   annotated objects. Images whose only annotations are damage codes we
   don't map (D43, D44, D0w0, etc.) are now SKIPPED instead of being
   silently mislabeled "intact" -- this was training the model to call
   visibly damaged roads "intact."
2. label_from_xml: when multiple mapped damage types co-occur in one image,
   the label is now the one with the LARGEST bounding box (dominant visible
   damage) instead of a fixed "pothole always wins" priority. This was
   inflating the pothole class with images that were mostly cracks.
3. Stratified train/val split instead of random_split, so the (already
   small) transverse_crack class isn't further skewed by chance.
4. Optional per-class-balanced subsampling so majority classes
   (intact_road, longitudinal_crack) don't drown out minority classes
   (transverse_crack) within MAX_SAMPLES.
5. Added horizontal-flip augmentation for training only. Rotation/vertical
   flip are deliberately NOT used because they would swap the visual
   meaning of longitudinal vs. transverse cracks.
"""

from __future__ import annotations

import argparse
import json
import random
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from sklearn.decomposition import PCA
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "rdd"
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

COUNTRIES = ["Japan", "India", "United_States", "Norway", "Czech"]
MODEL_ARCHITECTURE = "vgg16_svm"
SVM_KERNEL = "rbf"

# RDD2022 damage codes -> RoadWatch classes.
# NOTE: RDD2022 has more codes than these four (crosswalk blur, white-line
# blur, "other corruption", repairs, etc., depending on country). Those are
# now SKIPPED rather than folded into intact_road -- see label_from_xml.
RDD_TO_CLASS = {
    "D40": "pothole",
    "D20": "alligator_crack",
    "D00": "longitudinal_crack",
    "D10": "transverse_crack",
}

INTACT_LABEL = "intact_road"
CLASS_NAMES = [
    "pothole",
    "alligator_crack",
    "longitudinal_crack",
    "transverse_crack",
    INTACT_LABEL,
]
CLASS_TO_IDX = {name: i for i, name in enumerate(CLASS_NAMES)}

IMG_SIZE = 224
BATCH_SIZE = 32
TARGET_EPOCHS = 60
VAL_SPLIT = 0.15
SEED = 42
MAX_SAMPLES = 6000
# Cap on how many samples any single class can contribute when building the
# balanced training subset. None = no cap (use natural distribution).
MAX_PER_CLASS = 1400
PCA_COMPONENTS = 512
SVM_C = 1.0
SVM_GAMMA = "scale"
# Edge-orientation histogram bins (0-180 degrees), concatenated onto the CNN
# features. This explicitly encodes crack direction, which heavy PCA on
# global-pooled CNN features tends to blur away -- and direction is the
# *only* thing separating longitudinal_crack from transverse_crack.
ORIENTATION_BINS = 18
CHECKPOINT_PATH = MODEL_DIR / "road_damage_vgg16_svm.pt"
METADATA_PATH = MODEL_DIR / "model_metadata.json"


@dataclass
class Sample:
    image_path: Path
    label: int
    country: str
    rdd_codes: list[str]


def bbox_area(obj: ET.Element) -> int:
    box = obj.find("bndbox")
    if box is None:
        return 0
    xmin = int(float(box.findtext("xmin", "0")))
    ymin = int(float(box.findtext("ymin", "0")))
    xmax = int(float(box.findtext("xmax", "0")))
    ymax = int(float(box.findtext("ymax", "0")))
    return max(0, xmax - xmin) * max(0, ymax - ymin)


def label_from_xml(xml_path: Path) -> tuple[int | None, list[str]]:
    """Return (class_index or None, raw_codes).

    None means "skip this image" -- either it has damage annotations we
    don't have a mapped class for, and we refuse to guess.
    """
    root = ET.parse(xml_path).getroot()
    objects = root.findall("object")
    codes = [obj.findtext("name", "").strip() for obj in objects]
    codes = [c for c in codes if c]

    # Genuinely no annotated objects at all -> genuinely intact.
    if not codes:
        return CLASS_TO_IDX[INTACT_LABEL], codes

    mapped_objs = [
        (obj, obj.findtext("name", "").strip())
        for obj in objects
        if obj.findtext("name", "").strip() in RDD_TO_CLASS
    ]

    # Has damage annotations, but none of them are classes we recognize
    # (e.g. crosswalk blur, white-line blur, "other" corruption). Do NOT
    # call this intact -- skip it so it doesn't pollute the intact class.
    if not mapped_objs:
        return None, codes

    # Dominant damage = largest bounding box among recognized codes, not a
    # fixed "pothole always wins" priority. This stops a small incidental
    # pothole in an otherwise heavily-cracked image from stealing the label.
    best_code = None
    best_area = -1
    for obj, code in mapped_objs:
        area = bbox_area(obj)
        if area > best_area:
            best_area = area
            best_code = code

    return CLASS_TO_IDX[RDD_TO_CLASS[best_code]], codes


def balanced_subsample(samples: list[Sample], max_total: int, max_per_class: int | None) -> list[Sample]:
    """Cap majority classes so minority classes aren't drowned out."""
    by_class: dict[int, list[Sample]] = defaultdict(list)
    for s in samples:
        by_class[s.label].append(s)

    for items in by_class.values():
        random.shuffle(items)

    if max_per_class is not None:
        for label in by_class:
            by_class[label] = by_class[label][:max_per_class]

    result = [s for items in by_class.values() for s in items]
    random.shuffle(result)

    if max_total and len(result) > max_total:
        result = result[:max_total]

    return result


def build_samples() -> list[Sample]:
    samples: list[Sample] = []
    skipped_no_xml = 0
    skipped_unmapped_damage = 0

    for country in COUNTRIES:
        img_dir = DATA_DIR / country / "train" / "images"
        xml_dir = DATA_DIR / country / "train" / "annotations" / "xmls"
        if not img_dir.exists():
            raise FileNotFoundError(
                f"Missing extracted data for {country}. Run extract_rdd.py first."
            )

        for img_path in sorted(img_dir.glob("*.jpg")):
            xml_path = xml_dir / f"{img_path.stem}.xml"
            if not xml_path.exists():
                skipped_no_xml += 1
                continue
            label, codes = label_from_xml(xml_path)
            if label is None:
                skipped_unmapped_damage += 1
                continue
            samples.append(Sample(img_path, label, country, codes))

    random.seed(SEED)
    random.shuffle(samples)

    print(f"Built {len(samples)} labeled samples before balancing")
    print(f"  skipped (no xml):            {skipped_no_xml}")
    print(f"  skipped (unmapped damage):   {skipped_unmapped_damage}")

    samples = balanced_subsample(samples, MAX_SAMPLES, MAX_PER_CLASS)

    print(f"\nFinal training pool: {len(samples)} samples")
    counts = {name: 0 for name in CLASS_NAMES}
    for s in samples:
        counts[CLASS_NAMES[s.label]] += 1
    print("Class distribution:")
    for name, count in counts.items():
        print(f"  {name:22s} {count:6d}")
    return samples


class RoadDamageDataset(Dataset):
    def __init__(self, items: list[Sample], transform=None):
        self.items = items
        self.transform = transform

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int):
        item = self.items[idx]
        image = Image.open(item.image_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        return image, item.label


class VGG16FeatureExtractor(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        try:
            backbone = models.vgg16(weights=models.VGG16_Weights.DEFAULT)
            print("Loaded ImageNet pretrained VGG16 weights.")
        except Exception as exc:
            print(f"Pretrained VGG16 weights unavailable ({exc}). Training from scratch.")
            backbone = models.vgg16(weights=None)
        backbone.classifier = nn.Identity()
        for parameter in backbone.parameters():
            parameter.requires_grad_(False)
        self.backbone = backbone

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        features = self.backbone.features(images)
        features = self.backbone.avgpool(features)
        return torch.flatten(features, 1)


def build_feature_extractor() -> VGG16FeatureExtractor:
    return VGG16FeatureExtractor()


def crack_orientation_histogram(image_path: Path, bins: int = ORIENTATION_BINS) -> np.ndarray:
    """Explicit edge-direction signal to help separate longitudinal
    (running along the road) from transverse (running across the road)
    cracks -- something global-pooled + heavily-PCA'd CNN features are
    prone to blur away, since both classes look similar texturally and
    differ mainly by angle.
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return np.zeros(bins, dtype=np.float32)
    img = cv2.resize(img, (256, 256))
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx**2 + gy**2)
    # Direction-agnostic angle in [0, 180) -- a line and its opposite
    # direction are the same crack orientation.
    ang = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0

    # Only look at the strongest edges (crack boundaries), ignore noise/asphalt texture.
    threshold = np.percentile(mag, 90)
    mask = mag >= threshold
    if not np.any(mask):
        return np.zeros(bins, dtype=np.float32)

    hist, _ = np.histogram(ang[mask], bins=bins, range=(0, 180), weights=mag[mask])
    total = hist.sum()
    return (hist / total).astype(np.float32) if total > 0 else hist.astype(np.float32)


def compute_orientation_batch(items: list[Sample]) -> np.ndarray:
    return np.stack([
        crack_orientation_histogram(item.image_path)
        for item in tqdm(items, desc="orientation", leave=False)
    ])


def extract_features(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    all_features: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []

    with torch.no_grad():
        for images, labels in tqdm(loader, desc="extract", leave=False):
            images = images.to(device)
            features = model(images)
            all_features.append(features.cpu().numpy())
            all_labels.append(labels.cpu().numpy())

    return np.concatenate(all_features, axis=0), np.concatenate(all_labels, axis=0)


def train_svm(
    train_features: np.ndarray,
    train_labels: np.ndarray,
    pca_components: int,
    svm_c: float,
    svm_gamma: str | float,
) -> make_pipeline:
    n_components = min(max(2, pca_components), train_features.shape[1], max(2, train_features.shape[0] - 1))
    pipeline = make_pipeline(
        StandardScaler(),
        PCA(n_components=n_components, random_state=SEED),
        SVC(kernel=SVM_KERNEL, C=svm_c, gamma=svm_gamma, probability=True, random_state=SEED, class_weight="balanced"),
    )
    pipeline.fit(train_features, train_labels)
    return pipeline


def evaluate_svm(pipeline, features: np.ndarray, labels: np.ndarray) -> tuple[float, str, list[list[int]]]:
    preds = pipeline.predict(features)
    accuracy = float((preds == labels).mean())
    report = classification_report(labels, preds, target_names=CLASS_NAMES, digits=3, zero_division=0)
    cm = confusion_matrix(labels, preds).tolist()
    return accuracy, report, cm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train RoadWatch PH damage classifier")
    parser.add_argument("--max-samples", type=int, default=MAX_SAMPLES, help="Maximum number of labeled samples to use")
    parser.add_argument("--max-per-class", type=int, default=MAX_PER_CLASS, help="Cap per class before subsampling (0 = no cap)")
    parser.add_argument("--pca-components", type=int, default=PCA_COMPONENTS, help="PCA dimension for VGG16 features")
    parser.add_argument("--svm-c", type=float, default=SVM_C, help="C regularization for the RBF SVM")
    parser.add_argument("--svm-gamma", type=str, default=SVM_GAMMA, help="Gamma parameter for the RBF SVM")
    parser.add_argument("--target-epochs", type=int, default=TARGET_EPOCHS, help=f"Legacy epoch target kept for compatibility (default: {TARGET_EPOCHS})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)

    global MAX_PER_CLASS
    MAX_PER_CLASS = args.max_per_class if args.max_per_class > 0 else None

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    samples = build_samples()
    if len(samples) < 100:
        raise RuntimeError("Too few training samples. Check extraction.")

    # Train-time: mild augmentation only. Deliberately NO rotation/vertical
    # flip -- those would swap the visual meaning of longitudinal vs.
    # transverse cracks and corrupt the labels.
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

    labels = [s.label for s in samples]
    train_items, val_items = train_test_split(
        samples,
        test_size=VAL_SPLIT,
        random_state=SEED,
        stratify=labels,  # keep class proportions consistent in val set
    )

    train_ds = RoadDamageDataset(train_items, train_tf)
    val_ds = RoadDamageDataset(val_items, val_tf)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    feature_extractor = build_feature_extractor().to(device)
    print(f"\nTraining on {len(COUNTRIES)} countries: {', '.join(COUNTRIES)}")
    print(f"Train: {len(train_items)} | Val: {len(val_items)} | Samples: {len(samples)}")
    print("Training VGG16 + RBF-SVM classifier...\n")

    train_features, train_labels = extract_features(feature_extractor, train_loader, device)
    val_features, val_labels = extract_features(feature_extractor, val_loader, device)

    print("Computing crack-orientation features...")
    train_orient = compute_orientation_batch(train_items)
    val_orient = compute_orientation_batch(val_items)
    train_features = np.concatenate([train_features, train_orient], axis=1)
    val_features = np.concatenate([val_features, val_orient], axis=1)

    svm_pipeline = train_svm(train_features, train_labels, args.pca_components, args.svm_c, args.svm_gamma)
    val_acc, report, cm = evaluate_svm(svm_pipeline, val_features, val_labels)

    print("\nValidation report:")
    print(report)

    artifact = {
        "model_type": MODEL_ARCHITECTURE,
        "svm_kernel": SVM_KERNEL,
        "feature_extractor_state_dict": feature_extractor.state_dict(),
        "pipeline": svm_pipeline,
        "class_names": CLASS_NAMES,
        "countries": COUNTRIES,
        "img_size": IMG_SIZE,
        "best_val_accuracy": round(val_acc, 4),
        "total_samples": len(samples),
        "total_epochs": int(args.target_epochs),
        "target_epochs": args.target_epochs,
        "pca_components": int(args.pca_components),
        "svm_c": args.svm_c,
        "svm_gamma": args.svm_gamma,
        "orientation_bins": ORIENTATION_BINS,
        "history": [{"epoch": 1, "val_acc": round(val_acc, 4)}],
    }

    torch.save(artifact, CHECKPOINT_PATH)

    metadata = {
        "model_type": MODEL_ARCHITECTURE,
        "svm_kernel": SVM_KERNEL,
        "countries": COUNTRIES,
        "class_names": CLASS_NAMES,
        "rdd_to_class": RDD_TO_CLASS,
        "img_size": IMG_SIZE,
        "best_val_accuracy": round(val_acc, 4),
        "total_samples": len(samples),
        "total_epochs": int(args.target_epochs),
        "target_epochs": args.target_epochs,
        "pca_components": int(args.pca_components),
        "svm_c": args.svm_c,
        "svm_gamma": args.svm_gamma,
        "orientation_bins": ORIENTATION_BINS,
        "classification_report": report,
        "confusion_matrix": cm,
    }

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nSaved VGG16+SVM model to {CHECKPOINT_PATH}")
    print(f"Validation accuracy: {val_acc:.3f}")


if __name__ == "__main__":
    main()