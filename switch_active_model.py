"""
Switch which trained model predict.py/api.py will use, WITHOUT retraining
anything. This just rewrites model_metadata.json's pointer, using the info
already saved inside the .pt checkpoint file itself.

Usage:
    python switch_active_model.py finetuned
    python switch_active_model.py svm
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"
METADATA_PATH = MODEL_DIR / "model_metadata.json"

FINETUNED_PATH = MODEL_DIR / "road_damage_vgg16_finetuned.pt"
SVM_PATH = MODEL_DIR / "road_damage_vgg16_svm.pt"


def switch_to_finetuned() -> None:
    if not FINETUNED_PATH.exists():
        raise FileNotFoundError(f"No checkpoint found at {FINETUNED_PATH}")

    artifact = torch.load(FINETUNED_PATH, map_location="cpu", weights_only=False)

    metadata = {
        "model_type": "vgg16_finetuned",
        "checkpoint_filename": FINETUNED_PATH.name,
        "class_names": artifact["class_names"],
        "img_size": artifact["img_size"],
        "unfreeze_from": artifact.get("unfreeze_from"),
        "best_val_accuracy": artifact.get("best_val_accuracy"),
        "epoch": artifact.get("epoch"),
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Switched active model -> FINE-TUNED (epoch {artifact.get('epoch')}, "
          f"best_val_accuracy={artifact.get('best_val_accuracy')})")
    print(f"Wrote {METADATA_PATH}")


def switch_to_svm() -> None:
    if not SVM_PATH.exists():
        raise FileNotFoundError(f"No checkpoint found at {SVM_PATH}")

    artifact = torch.load(SVM_PATH, map_location="cpu", weights_only=False)

    metadata = {
        "model_type": "vgg16_svm",
        "checkpoint_filename": SVM_PATH.name,
        "class_names": artifact["class_names"],
        "img_size": artifact["img_size"],
        "svm_kernel": artifact.get("svm_kernel"),
        "orientation_bins": artifact.get("orientation_bins", 0),
        "best_val_accuracy": artifact.get("best_val_accuracy"),
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Switched active model -> SVM (best_val_accuracy={artifact.get('best_val_accuracy')})")
    print(f"Wrote {METADATA_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Switch active model without retraining")
    parser.add_argument("target", choices=["finetuned", "svm"])
    args = parser.parse_args()

    if args.target == "finetuned":
        switch_to_finetuned()
    else:
        switch_to_svm()


if __name__ == "__main__":
    main()
