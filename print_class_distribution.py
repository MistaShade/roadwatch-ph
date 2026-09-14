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
