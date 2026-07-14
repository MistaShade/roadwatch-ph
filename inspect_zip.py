import zipfile
from collections import Counter

path = r"C:\Users\Joshua\OneDrive\Documents\Pothole_Detector\RDD2022.zip"

with zipfile.ZipFile(path, "r") as z:
    names = z.namelist()
    print(f"Total entries: {len(names)}")

    print("\n--- First 50 paths ---")
    for n in names[:50]:
        info = z.getinfo(n)
        print(f"{info.file_size:>12}  {n}")

    print("\n--- Top-level folders ---")
    tops = Counter()
    for n in names:
        top = n.split("/")[0] if "/" in n else n.split("\\")[0]
        tops[top] += 1
    for k, v in sorted(tops.items(), key=lambda x: -x[1])[:25]:
        print(f"{v:>8}  {k}")

    exts = Counter()
    train_images = []
    for n in names:
        lower = n.lower()
        if lower.endswith((".jpg", ".jpeg", ".png")):
            exts[lower.rsplit(".", 1)[-1]] += 1
            if "train" in lower and len(train_images) < 20:
                train_images.append(n)

    print("\n--- Image extensions ---")
    for ext, count in exts.most_common():
        print(f"{count:>8}  .{ext}")

    print("\n--- Sample train image paths ---")
    for n in train_images:
        print(n)

    train_count = sum(
        1
        for n in names
        if "train" in n.lower() and n.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    print(f"\nTrain images (approx): {train_count}")
