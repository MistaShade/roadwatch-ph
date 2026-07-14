import io
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter

main_path = r"C:\Users\Joshua\OneDrive\Documents\Pothole_Detector\RDD2022.zip"
nested = "RDD2022_all_countries/Japan.zip"

with zipfile.ZipFile(main_path, "r") as outer:
    data = outer.read(nested)

with zipfile.ZipFile(io.BytesIO(data), "r") as japan:
    xml_paths = [n for n in japan.namelist() if n.endswith(".xml")][:500]
    labels = Counter()
    sample_xml = None
    for xp in xml_paths:
        root = ET.fromstring(japan.read(xp))
        for obj in root.findall(".//object"):
            name = obj.findtext("name", "").strip()
            if name:
                labels[name] += 1
        if sample_xml is None:
            sample_xml = japan.read(xml_paths[0]).decode("utf-8", errors="replace")

print("Damage labels (from first 500 annotation files):")
for label, count in labels.most_common():
    print(f"  {count:>5}  {label}")

print("\n--- Sample annotation XML (first file) ---")
print(sample_xml[:2000])
