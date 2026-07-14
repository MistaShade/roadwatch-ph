import io
import zipfile
from collections import Counter

main_path = r"C:\Users\Joshua\OneDrive\Documents\Pothole_Detector\RDD2022.zip"
nested = "RDD2022_all_countries/Japan.zip"

with zipfile.ZipFile(main_path, "r") as outer:
    print("Nested archives inside RDD2022.zip:")
    for info in outer.infolist():
        size_mb = info.file_size / (1024 * 1024)
        print(f"  {size_mb:>10.1f} MB  {info.filename}")

    print(f"\nReading listing from: {nested}")
    data = outer.read(nested)

with zipfile.ZipFile(io.BytesIO(data), "r") as japan:
    names = japan.namelist()
    print(f"Total entries in Japan.zip: {len(names)}")

    print("\n--- First 40 paths ---")
    for n in names[:40]:
        info = japan.getinfo(n)
        print(f"{info.file_size:>10}  {n}")

    print("\n--- Top-level folders ---")
    tops = Counter()
    for n in names:
        top = n.replace("\\", "/").split("/")[0]
        tops[top] += 1
    for k, v in sorted(tops.items(), key=lambda x: -x[1]):
        print(f"{v:>8}  {k}")

    exts = Counter()
    for n in names:
        lower = n.lower()
        if lower.endswith((".jpg", ".jpeg", ".png", ".xml", ".txt", ".json")):
            exts[lower.rsplit(".", 1)[-1]] += 1

    print("\n--- File types ---")
    for ext, count in exts.most_common():
        print(f"{count:>8}  .{ext}")

    train_imgs = [
        n for n in names
        if "train" in n.lower() and n.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    test_imgs = [
        n for n in names
        if "test" in n.lower() and n.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    print(f"\nTrain images: {len(train_imgs)}")
    print(f"Test images:  {len(test_imgs)}")

    if train_imgs:
        print("\n--- Sample train images ---")
        for n in train_imgs[:10]:
            print(n)

    ann = [n for n in names if n.lower().endswith(".xml")]
    if ann:
        print("\n--- Sample annotation files ---")
        for n in ann[:5]:
            print(n)
