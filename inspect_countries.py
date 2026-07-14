import io
import zipfile
from collections import Counter

main_path = r"C:\Users\Joshua\OneDrive\Documents\Pothole_Detector\RDD2022.zip"
countries = [
    "RDD2022_all_countries/Japan.zip",
    "RDD2022_all_countries/India.zip",
    "RDD2022_all_countries/United_States.zip",
]

with zipfile.ZipFile(main_path, "r") as outer:
    for nested in countries:
        name = nested.split("/")[-1].replace(".zip", "")
        print(f"\n=== {name} ===")
        data = outer.read(nested)
        with zipfile.ZipFile(io.BytesIO(data), "r") as inner:
            names = inner.namelist()
            train_imgs = [n for n in names if "/train/images/" in n.replace("\\", "/") and n.lower().endswith(".jpg")]
            test_imgs = [n for n in names if "/test/images/" in n.replace("\\", "/") and n.lower().endswith(".jpg")]
            xmls = [n for n in names if n.lower().endswith(".xml")]
            print(f"  train images: {len(train_imgs)}")
            print(f"  test images:  {len(test_imgs)}")
            print(f"  xml labels:   {len(xmls)}")
            if train_imgs:
                print(f"  sample image: {train_imgs[0]}")
            if xmls:
                print(f"  sample xml:   {xmls[0]}")
