"""Typed inputs and outputs. Particle measurements are in pixels, not mm."""

from dataclasses import dataclass
from math import isfinite
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
ImageArray = NDArray[np.uint8]


def validate_scale(pixel_scale: float) -> float:
    """Validate the calibration in pixels per millimeter."""
    if not isfinite(pixel_scale) or pixel_scale <= 0:
        raise ValueError("Pixel scale must be a finite positive number (pixels/mm).")
    return pixel_scale


@dataclass(frozen=True)
class AnalysisParameters:
    threshold: float = 58.8
    max_cluster_axis: float = 100.0
    min_surface: float = 5.0
    min_roundness: float = 0.0
    reference_threshold: float = 0.4
    maxcost: float = 0.35
    quick: bool = False

    def __post_init__(self) -> None:
        values = (
            self.threshold,
            self.max_cluster_axis,
            self.min_surface,
            self.min_roundness,
            self.reference_threshold,
            self.maxcost,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("Analysis parameters must be finite numbers.")
        if not 0 <= self.threshold <= 100:
            raise ValueError("Threshold must be between 0 and 100 percent.")
        if self.max_cluster_axis <= 0 or self.min_surface < 1:
            raise ValueError(
                "Maximum axis must be positive and minimum surface at least 1."
            )
        if self.min_roundness < 0 or self.maxcost < 0:
            raise ValueError("Roundness and maximum cost must be nonnegative.")
        if not 0 <= self.reference_threshold <= 1:
            raise ValueError("Reference threshold must be between 0 and 1.")


@dataclass(frozen=True)
class ThresholdResult:
    blue: ImageArray
    indices: tuple[IntArray, IntArray]
    boundary_indices: IntArray | None
    background_median: float


class Cluster(TypedDict):
    """Legacy field names retained for the cluster editing UI."""

    CLUSTER_ID: int
    SURFACE: float
    XLIST: IntArray
    YLIST: IntArray
    LONG_AXIS: float
    ROUNDNESS: float
    VOLUME: float
    SHORT_AXIS: float
    XMEAN: float
    YMEAN: float
    XSTART: int
    YSTART: int
    ZLIST: FloatArray
    ICLUST_FILTERED: IntArray
    ICLUST: IntArray
    MAXCOST_ALONG_PATH: FloatArray
    COST: FloatArray


@dataclass(frozen=True)
class Measurements:
    surface: FloatArray
    roundness: FloatArray
    short_axis: FloatArray
    long_axis: FloatArray
    volume: FloatArray

    def __post_init__(self) -> None:
        arrays = (
            self.surface,
            self.roundness,
            self.short_axis,
            self.long_axis,
            self.volume,
        )
        if any(array.ndim != 1 or array.size != self.surface.size for array in arrays):
            raise ValueError("Particle measurements must be equal-length vectors.")
        if any(not np.isfinite(array).all() for array in arrays):
            raise ValueError("Particle measurements must be finite.")
        if any(
            np.any(array <= 0)
            for array in (self.surface, self.short_axis, self.long_axis, self.volume)
        ) or np.any(self.roundness < 0):
            raise ValueError(
                "Particle sizes must be positive and roundness nonnegative."
            )

    @property
    def count(self) -> int:
        return self.surface.size


@dataclass(frozen=True)
class DetectionResult:
    clusters: list[Cluster]
    measurements: Measurements


@dataclass(frozen=True)
class Statistics:
    average_diameter: float
    diameter_stddev: float
    average_surface: float
    surface_stddev: float
    efficiency: float
    quality: float

    def legacy_values(self) -> dict[str, float]:
        """Match the legacy display precision used by the statistics CSV."""
        return {
            "AVG_DIAM": float(f"{self.average_diameter:.2f}"),
            "STD_DIAM": float(f"{self.diameter_stddev:.2f}"),
            "AVG_SURF": float(f"{self.average_surface:.2f}"),
            "STD_SURF": float(f"{self.surface_stddev:.2f}"),
            "EFF": float(f"{self.efficiency:.1f}"),
            "QUAL": float(f"{self.quality:.2f}"),
        }


HISTOGRAM_KINDS = tuple(
    f"{weight} vs {size}"
    for weight in ("Number", "Mass", "Available mass", "Surface")
    for size in ("Diameter", "Surface", "Volume")
)


@dataclass(frozen=True)
class HistogramOptions:
    kind: str = "Available mass vs Surface"
    log: bool = True
    auto_range: bool = True
    minimum: float = 0.01
    maximum: float = 10.0
    bin_count: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in HISTOGRAM_KINDS:
            raise ValueError(f"Unknown histogram option: {self.kind}")
        if self.bin_count is not None and self.bin_count < 2:
            raise ValueError("At least two bin edges are required.")
        if not self.auto_range:
            if (
                not (isfinite(self.minimum) and isfinite(self.maximum))
                or self.maximum <= self.minimum
            ):
                raise ValueError("Histogram bounds must be finite and increasing.")
            if self.log and self.minimum <= 0:
                raise ValueError("Logarithmic histogram bounds must be positive.")


@dataclass(frozen=True)
class Histogram:
    edges: FloatArray
    values: FloatArray
    centers: FloatArray
    poisson_negative: FloatArray
    poisson_positive: FloatArray
    average: float
    average_negative: float
    average_positive: float
    xlabel: str
    ylabel: str
