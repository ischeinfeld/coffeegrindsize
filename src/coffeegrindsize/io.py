"""Image loading and backward-compatible CSV input/output."""

from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from .core import calculate_statistics
from .models import Measurements, validate_scale

PARTICLE_COLUMNS = (
    "SURFACE",
    "ROUNDNESS",
    "SHORT_AXIS",
    "LONG_AXIS",
    "VOLUME",
    "PIXEL_SCALE",
)


def load_image(filename: str | Path) -> Image.Image:
    """Read an 8-bit image as RGB, compositing transparency onto white."""
    with Image.open(filename) as source:
        if source.mode not in {"1", "L", "LA", "P", "PA", "RGB", "RGBA", "CMYK"}:
            raise ValueError(
                f"Unsupported image mode {source.mode}. Use an 8-bit PNG or JPEG."
            )
        if "A" in source.getbands() or "transparency" in source.info:
            rgba = source.convert("RGBA")
            return Image.alpha_composite(
                Image.new("RGBA", source.size, "white"), rgba
            ).convert("RGB")
        return source.convert("RGB")


def read_measurements(filename: str | Path) -> tuple[Measurements, float]:
    """Read legacy CSVs, ignoring their ID/index column."""
    frame = pd.read_csv(filename)
    missing = set(PARTICLE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError("Missing particle CSV columns: " + ", ".join(sorted(missing)))
    if frame.empty:
        raise ValueError("The CSV contains no particles.")
    arrays = [frame[name].to_numpy(dtype=float) for name in PARTICLE_COLUMNS]
    scale = validate_scale(float(arrays[-1][0]))
    if not np.all(arrays[-1] == scale):
        raise ValueError("All CSV rows must use the same finite positive pixel scale.")
    return Measurements(*arrays[:-1]), scale


def write_measurements(
    filename: str | Path, data: Measurements, pixel_scale: float
) -> Path:
    """Write legacy particle CSV and its adjacent, rounded statistics CSV."""
    pixel_scale = validate_scale(pixel_scale)
    statistics = calculate_statistics(data, pixel_scale)
    destination = Path(filename)
    frame = pd.DataFrame(
        {
            "SURFACE": data.surface,
            "ROUNDNESS": data.roundness,
            "SHORT_AXIS": data.short_axis,
            "LONG_AXIS": data.long_axis,
            "VOLUME": data.volume,
            "PIXEL_SCALE": pixel_scale,
        }
    )
    frame.index.name = "ID"
    frame.to_csv(destination)
    stats_destination = destination.with_name(destination.stem + "_stats.csv")
    pd.DataFrame(
        {name: [value] for name, value in statistics.legacy_values().items()}
    ).to_csv(stats_destination)
    return stats_destination
