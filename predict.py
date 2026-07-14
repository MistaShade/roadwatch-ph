"""Run inference with the trained VGG16 + RBF-SVM road damage model."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "road_damage_vgg16_svm.pt"
LEGACY_MODEL_PATH = MODEL_DIR / "road_damage_mobilenet.pt"
META_PATH = MODEL_DIR / "model_metadata.json"

INTACT_LABEL = "intact_road"
UI_LABELS = {
    "pothole": "Pothole",
    "alligator_crack": "Alligator Crack",
    "longitudinal_crack": "Longitudinal Crack",
    "transverse_crack": "Transverse Crack",
    "intact_road": "Intact Road",
}
UI_COLORS = {
    "pothole": "#ef4444",
    "alligator_crack": "#a855f7",
    "longitudinal_crack": "#f97316",
    "transverse_crack": "#eab308",
    "intact_road": "#14b8a6",
}


class VGG16FeatureExtractor(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.backbone = models.vgg16(weights=None)
        self.backbone.classifier = nn.Identity()

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        features = self.backbone.features(images)
        features = self.backbone.avgpool(features)
        return torch.flatten(features, 1)


class VGG16Finetuned(nn.Module):
    """Must exactly match the architecture in finetune_vgg16.py's
    VGG16Finetuner, or the saved state_dict won't load correctly."""

    def __init__(self, num_classes: int) -> None:
        super().__init__()
        backbone = models.vgg16(weights=None)
        self.features = backbone.features
        self.avgpool = backbone.avgpool
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(512 * 7 * 7, 512),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(512, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.avgpool(x)
        return self.classifier(x)


def load_metadata() -> dict:
    with open(META_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_prediction_items(ranked_items: list[tuple[str, float]], top_n: int = 3) -> list[dict]:
    return [
        {
            "type": class_name,
            "label": UI_LABELS.get(class_name, class_name.replace("_", " ").title()),
            "confidence": round(float(probability) * 100, 1),
            "color": UI_COLORS.get(class_name, "#6b7280"),
        }
        for class_name, probability in ranked_items[:top_n]
    ]


def build_top_predictions(class_names: list[str], probabilities: list[float], top_n: int = 3) -> list[dict]:
    ranked = sorted(
        zip(class_names, probabilities),
        key=lambda item: item[1],
        reverse=True,
    )
    return build_prediction_items(ranked, top_n)


def build_top_predictions_from_probabilities(probabilities: dict[str, float], top_n: int = 3) -> list[dict]:
    ranked = sorted(probabilities.items(), key=lambda item: float(item[1]), reverse=True)
    return build_prediction_items(ranked, top_n)


def select_primary_class(class_names: list[str], probabilities: list[float]) -> int:
    if not class_names:
        raise ValueError("class_names cannot be empty")

    best_idx = int(np.argmax(probabilities))
    best_prob = float(probabilities[best_idx])

    if class_names[best_idx] == INTACT_LABEL and len(class_names) > 1:
        damage_candidates = [
            (idx, float(prob))
            for idx, prob in enumerate(probabilities)
            if class_names[idx] != INTACT_LABEL and idx != best_idx
        ]
        if damage_candidates:
            highest_damage_idx, highest_damage_prob = max(damage_candidates, key=lambda item: item[1])
            if highest_damage_prob >= best_prob - 0.08:
                return highest_damage_idx

    return best_idx


def build_feature_extractor() -> nn.Module:
    return VGG16FeatureExtractor()


def resolve_orientation_bins(artifact: dict, metadata: dict) -> int:
    for candidate in (artifact, metadata):
        value = candidate.get("orientation_bins") if isinstance(candidate, dict) else None
        if isinstance(value, int) and value > 0:
            return value
    return 0


def crack_orientation_histogram(image_path: str | Path, bins: int) -> np.ndarray:
    """Must exactly mirror the function of the same name in train_model.py --
    this is what turns crack direction into an explicit feature so the SVM
    can tell longitudinal_crack and transverse_crack apart. If you change
    one copy, change the other, or predictions will silently drift from
    what the model was trained on.
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return np.zeros(bins, dtype=np.float32)
    img = cv2.resize(img, (256, 256))
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx**2 + gy**2)
    ang = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0

    threshold = np.percentile(mag, 90)
    mask = mag >= threshold
    if not np.any(mask):
        return np.zeros(bins, dtype=np.float32)

    hist, _ = np.histogram(ang[mask], bins=bins, range=(0, 180), weights=mag[mask])
    total = hist.sum()
    return (hist / total).astype(np.float32) if total > 0 else hist.astype(np.float32)


def load_model(device: torch.device | None = None):
    device = device or torch.device("cpu")
    meta = load_metadata()
    class_names = meta["class_names"]

    checkpoint_filename = meta.get("checkpoint_filename")
    if checkpoint_filename:
        model_path = MODEL_DIR / checkpoint_filename
    else:
        model_path = MODEL_PATH if MODEL_PATH.exists() else LEGACY_MODEL_PATH

    artifact = torch.load(model_path, map_location=device, weights_only=False)
    model_type = artifact.get("model_type") if isinstance(artifact, dict) else None

    if model_type == "vgg16_finetuned":
        model = VGG16Finetuned(len(class_names)).to(device)
        model.load_state_dict(artifact["state_dict"])
        model.eval()
        return {
            "type": "vgg16_finetuned",
            "model": model,
            "meta": meta,
            "device": device,
        }, class_names, device

    if model_type == "vgg16_svm":
        feature_extractor = build_feature_extractor().to(device)
        feature_extractor.load_state_dict(artifact["feature_extractor_state_dict"])
        feature_extractor.eval()
        orientation_bins = resolve_orientation_bins(artifact, meta)
        return {
            "type": "vgg16_svm",
            "feature_extractor": feature_extractor,
            "pipeline": artifact["pipeline"],
            "meta": meta,
            "device": device,
            "orientation_bins": orientation_bins,
        }, class_names, device

    raise RuntimeError(f"Unrecognized model_type in checkpoint: {model_type!r}")


def predict_image(image_path: str | Path, device: torch.device | None = None) -> dict:
    bundle, class_names, device = load_model(device)
    meta = bundle["meta"]
    img_size = meta.get("img_size", 224)

    transform = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    image = Image.open(image_path).convert("RGB")
    tensor = transform(image).unsqueeze(0).to(device)

    if bundle["type"] == "vgg16_finetuned":
        with torch.no_grad():
            logits = bundle["model"](tensor)
            probs = torch.softmax(logits, dim=1)[0].cpu().numpy()
    else:  # vgg16_svm
        with torch.no_grad():
            features = bundle["feature_extractor"](tensor)
            features = features.cpu().numpy().reshape(1, -1)

        orientation_bins = bundle["orientation_bins"]
        if orientation_bins > 0:
            orient = crack_orientation_histogram(image_path, orientation_bins).reshape(1, -1)
            features = np.concatenate([features, orient], axis=1)

        probs = bundle["pipeline"].predict_proba(features)[0]

    best_idx = select_primary_class(class_names, probs.tolist())
    best_conf = float(probs[best_idx] * 100)
    top_predictions = build_top_predictions(class_names, probs.tolist(), top_n=3)

    return {
        "type": class_names[best_idx],
        "label": top_predictions[0]["label"],
        "confidence": round(best_conf, 1),
        "color": top_predictions[0]["color"],
        "probabilities": {
            class_names[i]: round(float(probs[i]) * 100, 2) for i in range(len(class_names))
        },
        "top_predictions": top_predictions,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python predict.py <image_path>")
        raise SystemExit(1)

    result = predict_image(sys.argv[1])
    print(json.dumps(result, indent=2))