"""
Quick utility: print the exact class distribution used in training,
without running any training. Just calls the same sample-building logic
train_model.py / finetune_vgg16.py use internally.

Usage (match whatever settings you actually trained with):
    python print_class_distribution.py --max-samples 15000 --max-per-class 3500
"""

from __future__ import annotations

import argparse

import train_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-samples", type=int, default=6000)
    parser.add_argument("--max-per-class", type=int, default=1400)
    args = parser.parse_args()

    train_model.MAX_SAMPLES = args.max_samples
    train_model.MAX_PER_CLASS = args.max_per_class

    samples = train_model.build_samples()
    print(f"\nTotal samples used: {len(samples)}")


if __name__ == "__main__":
    main()
