"""
Extract train images + XML annotations for selected RDD2022 countries
from the nested archives inside RDD2022.zip.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent
ZIP_PATH = ROOT / "RDD2022.zip"
OUT_DIR = ROOT / "data" / "rdd"

COUNTRIES = {
    "Japan": "RDD2022_all_countries/Japan.zip",
    "India": "RDD2022_all_countries/India.zip",
    "United_States": "RDD2022_all_countries/United_States.zip",
    "Norway": "RDD2022_all_countries/Norway.zip",
    "Czech": "RDD2022_all_countries/Czech.zip",
}


def should_extract(name: str) -> bool:
    norm = name.replace("\\", "/")
    return (
        "/train/images/" in norm
        and norm.lower().endswith(".jpg")
    ) or (
        "/train/annotations/xmls/" in norm
        and norm.lower().endswith(".xml")
    )


def extract_country(outer: zipfile.ZipFile, country: str, nested_path: str) -> int:
    country_dir = OUT_DIR / country
    count = 0

    print(f"\nExtracting {country}...")
    blob = outer.read(nested_path)

    with zipfile.ZipFile(io.BytesIO(blob), "r") as inner:
        members = [m for m in inner.namelist() if should_extract(m)]
        for member in tqdm(members, desc=country, unit="file"):
            rel = member.replace("\\", "/")
            # Japan/train/images/foo.jpg -> train/images/foo.jpg
            parts = rel.split("/", 1)
            if len(parts) < 2:
                continue
            dest = country_dir / parts[1]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(inner.read(member))
            count += 1

    return count


def main() -> None:
    if not ZIP_PATH.exists():
        raise FileNotFoundError(f"Missing dataset archive: {ZIP_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0

    with zipfile.ZipFile(ZIP_PATH, "r") as outer:
        for country, nested in COUNTRIES.items():
            total += extract_country(outer, country, nested)

    print(f"\nDone. Extracted {total} files to {OUT_DIR}")


if __name__ == "__main__":
    main()
