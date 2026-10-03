"""Regenerate regression fixtures from the pinned upstream implementation."""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from legacy import legacy, snapshot, synthetic_image  # noqa: E402


def main():
    fixtures = ROOT / "tests" / "fixtures"
    images = {"synthetic": synthetic_image()}
    # Fixed full-resolution crops; no resizing or preprocessing changes.
    for name, box in [("Better", (800, 800, 928, 928)), ("Decent", (800, 800, 928, 928))]:
        with Image.open(ROOT / "Help" / f"{name}_Example_Picture.png") as image:
            crop = image.convert("RGB").crop(box)
            crop.save(fixtures / f"{name.lower()}_crop.png")
            images[name.lower()] = np.asarray(crop)
    captured = {}
    for name, image in images.items():
        for quick in (False, True):
            print(f"Capturing {name}, quick={quick}", flush=True)
            captured[f"{name}_{'quick' if quick else 'full'}"] = snapshot(legacy(image, quick=quick))
    (fixtures / "baseline.json").write_text(json.dumps(captured, indent=2, allow_nan=True) + "\n")


if __name__ == "__main__":
    main()
