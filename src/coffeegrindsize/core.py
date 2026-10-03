"""Numerical analysis independent of Tk, file dialogs, and plotting state.

The detector below is extracted from Jonathan Gagné's original algorithm.
Preserve ordering, connectivity, filtering, and volume conventions until a
separate scientific-model change is explicitly reviewed.
"""

from collections.abc import Callable, Sequence
from typing import Any, cast

import numpy as np
from matplotlib.path import Path

from .models import (
    AnalysisParameters,
    Cluster,
    DetectionResult,
    FloatArray,
    Histogram,
    HistogramOptions,
    ImageArray,
    IntArray,
    Measurements,
    Statistics,
    ThresholdResult,
    validate_scale,
)

NSMOOTH = 3
COFFEE_CELL_SIZE = 20.0  # microns
DEFAULT_PARAMETERS = AnalysisParameters()
DEFAULT_HISTOGRAM_OPTIONS = HistogramOptions()


def threshold_image(
    image: ImageArray,
    parameters: AnalysisParameters = DEFAULT_PARAMETERS,
    polygon: FloatArray | None = None,
) -> ThresholdResult:
    """Threshold the blue channel; polygon coordinates are (column, row)."""
    if (
        image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or not image.size
    ):
        raise ValueError("Analysis requires a nonempty uint8 RGB image.")
    blue = image[:, :, 2]
    poly = None
    if polygon is not None:
        if (
            polygon.ndim != 2
            or polygon.shape[1] != 2
            or polygon.shape[0] < 3
            or not np.isfinite(polygon).all()
        ):
            raise ValueError(
                "An analysis polygon needs at least three finite (x, y) points."
            )
        if not np.array_equal(polygon[0], polygon[-1]):
            polygon = np.vstack((polygon, polygon[0]))
        poly = Path(polygon)
        rows, columns = np.indices(blue.shape)
        contained = poly.contains_points(
            np.column_stack((columns.ravel(), rows.ravel()))
        )
        if not contained.any():
            raise ValueError("No image pixels are inside the analysis region.")
        background = float(np.median(blue.ravel()[contained]))
    else:
        background = float(np.median(blue))
    indices = cast(
        tuple[IntArray, IntArray],
        np.where(blue < background * parameters.threshold / 100),
    )
    boundary = None
    if poly is not None and polygon is not None:
        inside = poly.contains_points(np.column_stack((indices[1], indices[0])))
        indices = (indices[0][inside], indices[1][inside])
        boundary = points_along_polygon(
            indices[1].astype(float),
            indices[0].astype(float),
            polygon[:, 0],
            polygon[:, 1],
        )
    return ThresholdResult(blue, indices, boundary, background)


def measurements_from_clusters(clusters: Sequence[Cluster]) -> Measurements:
    """Collect raw pixel measurements, including an empty detection result."""
    return Measurements(
        *(
            np.asarray([c[key] for c in clusters], dtype=float)
            for key in ("SURFACE", "ROUNDNESS", "SHORT_AXIS", "LONG_AXIS", "VOLUME")
        )
    )


def calculate_statistics(data: Measurements, pixel_scale: float) -> Statistics:
    """Compute legacy mass-weighted statistics in millimeters."""
    validate_scale(pixel_scale)
    if not data.count:
        raise ValueError("No particles are available for statistics.")
    diameters = 2 * np.sqrt(data.long_axis * data.short_axis) / pixel_scale
    surfaces = data.surface / pixel_scale**2
    volumes = data.volume / pixel_scale**3
    masses = attainable_mass_simulate(volumes)
    weights = np.maximum(np.ceil(masses / (COFFEE_CELL_SIZE / 1e3) ** 3), 1)
    diameter_average = float(np.sum(diameters * weights) / np.sum(weights))
    diameter_stddev = weighted_stddev(diameters, weights, frequency=True)
    # weighted_stddev must not mutate the caller's weights.
    surface_average = float(np.sum(surfaces * weights) / np.sum(weights))
    surface_stddev = weighted_stddev(surfaces, weights, frequency=True)
    quality = surface_average / surface_stddev if surface_stddev > 0 else float("nan")
    return Statistics(
        diameter_average,
        diameter_stddev,
        surface_average,
        surface_stddev,
        float(np.mean(masses / volumes) * 100),
        quality,
    )


def prepare_histogram(
    data: Measurements,
    pixel_scale: float,
    options: HistogramOptions = DEFAULT_HISTOGRAM_OPTIONS,
    edges: FloatArray | None = None,
) -> Histogram:
    """Prepare normalized histogram values and legacy Poisson/CDF estimates."""
    validate_scale(pixel_scale)
    if not data.count:
        raise ValueError("No particles are available for a histogram.")
    weight_kind, size_kind = options.kind.split(" vs ")
    if size_kind == "Diameter":
        values = 2 * np.sqrt(data.long_axis * data.short_axis) / pixel_scale
        xlabel = "Particle Diameter (mm)"
    elif size_kind == "Surface":
        values = data.surface / pixel_scale**2
        xlabel = "Particle Surface (mm$^2$)"
    else:
        values = data.volume / pixel_scale**3
        xlabel = "Particle Volume (mm$^3$)"
    if weight_kind == "Number":
        weights = np.ones(data.count)
        ylabel = "Fraction of Particles"
    elif weight_kind == "Surface":
        weights = data.surface
        ylabel = "Fraction of Total Surface"
    elif weight_kind == "Mass":
        weights = data.volume
        ylabel = "Fraction of Total Mass"
    else:
        weights = attainable_mass_simulate(data.volume / pixel_scale**3)
        ylabel = "Fraction of Available Mass"
    xmin, xmax = (
        (float(values.min()), float(values.max()))
        if options.auto_range
        else (options.minimum, options.maximum)
    )
    if edges is None:
        if xmin == xmax:
            xmin, xmax = (
                (xmin * 0.95, xmax * 1.05)
                if options.log
                else (xmin - 0.05, xmax + 0.05)
            )
        if options.bin_count is not None:
            count = options.bin_count
        elif options.log:
            # Preserve the original bin-count expression, including its parentheses.
            count = max(2, int(np.ceil(np.log10(xmax - np.log10(xmin)) / 0.05)))
        else:
            count = max(2, int(np.ceil((xmax - xmin) / 0.1)))
        edges = (
            np.logspace(np.log10(xmin), np.log10(xmax), count)
            if options.log
            else np.linspace(xmin, xmax, count)
        )
    if (
        edges.ndim != 1
        or edges.size < 2
        or not np.isfinite(edges).all()
        or np.any(np.diff(edges) <= 0)
        or (options.log and np.any(edges <= 0))
    ):
        raise ValueError("Histogram bin edges must be finite and strictly increasing.")
    total = np.nansum(weights)
    heights, _ = np.histogram(values, bins=edges, weights=weights / total)
    centers = edges[:-1] + np.diff(edges) / 2
    negative = np.full(edges.size - 1, np.nan)
    positive = np.full(edges.size - 1, np.nan)
    for i in range(edges.size - 1):
        inside = (values >= edges[i]) & (values < edges[i + 1])
        n = int(inside.sum())
        if n:
            average_weight = float(weights[inside].mean() / total)
            positive[i] = (0.5 + np.sqrt(n + 0.25)) * average_weight
            negative[i] = (-0.5 + np.sqrt(n + 0.25)) * average_weight
    if not heights.sum():
        raise ValueError("The selected histogram range contains no particles.")
    average = float(np.nansum(heights * centers) / np.nansum(heights))
    cdf = np.nancumsum(heights) / np.nansum(heights)
    left, right = centers < average, centers >= average

    def spread(mask: Any, reverse: bool) -> float:
        if not mask.any():
            return 0.0
        portion = -cdf[mask] if reverse else cdf[mask]
        portion = portion - np.nanmin(portion)
        if not np.nanmax(portion):
            # np.interp historically returns the sole bin center even with a
            # NaN CDF. Keep that endpoint for varied data; constant data has
            # no spread and previously had undefined error bars.
            if mask.sum() == 1 and np.ptp(values) > 0:
                return abs(float(centers[mask][0]) - average)
            return 0.0
        portion = portion / np.nanmax(portion)
        positions = centers[mask]
        if reverse:
            portion, positions = np.flip(portion), np.flip(positions)
        return abs(float(np.interp(0.68268949, portion, positions)) - average)

    return Histogram(
        edges,
        heights,
        centers,
        negative,
        positive,
        average,
        spread(left, True),
        spread(right, False),
        xlabel,
        ylabel,
    )


def quick_cluster(
    xlist: FloatArray, ylist: FloatArray, xstart: float, ystart: float
) -> IntArray:
    xcheck = np.array([xstart])
    ycheck = np.array([ystart])
    xlist_decay = np.copy(xlist)
    ylist_decay = np.copy(ylist)
    ilist_decay = np.arange(xlist.size)
    istart = np.where((xlist_decay == xstart) & (ylist_decay == ystart))
    if istart[0].size != 0:
        xlist_decay = np.delete(xlist_decay, istart[0])
        ylist_decay = np.delete(ylist_decay, istart[0])
        ilist_decay = np.delete(ilist_decay, istart[0])
    iout = istart[0]
    for _i in range(xlist.size):
        isel = np.where(
            np.abs(xlist_decay - xcheck[0]) + np.abs(ylist_decay - ycheck[0]) <= 1.001
        )
        if isel[0].size == 0:
            if xcheck.size == 1:
                break
            xcheck = np.delete(xcheck, 0)
            ycheck = np.delete(ycheck, 0)
            continue
        iout = np.append(iout, ilist_decay[isel[0]])
        xcheck = np.append(xcheck, xlist_decay[isel[0]])
        ycheck = np.append(ycheck, ylist_decay[isel[0]])
        xcheck = np.delete(xcheck, 0)
        ycheck = np.delete(ycheck, 0)
        if isel[0].size == xlist_decay.size:
            break
        xlist_decay = np.delete(xlist_decay, isel[0])
        ylist_decay = np.delete(ylist_decay, isel[0])
        ilist_decay = np.delete(ilist_decay, isel[0])
    return np.asarray(iout, dtype=np.int64)


def smooth(x: FloatArray, window_size: int) -> FloatArray:
    window = np.ones(int(window_size)) / float(window_size)
    return np.convolve(x, window, "same")


def points_along_polygon(
    X_points: FloatArray,
    Y_points: FloatArray,
    X_polygon: FloatArray,
    Y_polygon: FloatArray,
) -> IntArray:
    nlines = X_polygon.size - 1
    x0 = X_points
    y0 = Y_points
    triggered = np.zeros(x0.size, dtype=bool)
    for li in range(nlines):
        x1 = X_polygon[li]
        y1 = Y_polygon[li]
        x2 = X_polygon[li + 1]
        y2 = Y_polygon[li + 1]
        ddline = np.abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1) / np.sqrt(
            (y2 - y1) ** 2 + (x2 - x1) ** 2
        )
        dd1 = np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
        dd2 = np.sqrt((x2 - x0) ** 2 + (y2 - y0) ** 2)
        dd12 = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        ipath = np.where(
            (ddline <= np.sqrt(2.0) * 1.01) & (dd1 <= dd12) & (dd2 <= dd12)
        )
        triggered[ipath[0]] = True
    ipath_all = np.where(triggered)
    return ipath_all[0]


def attainable_mass_simulate(volumes: FloatArray) -> FloatArray:
    depth_limit = 0.1
    radii = (3.0 / 4.0 * volumes / np.pi) ** (1 / 3)
    unreachable_volumes = np.full(volumes.size, 0.0)
    iboulders = np.where(radii > depth_limit)
    unreachable_volumes[iboulders[0]] = (
        4.0 / 3.0 * np.pi * (radii[iboulders[0]] - depth_limit) ** 3
    )
    reachable_volumes = volumes - unreachable_volumes
    return np.asarray(reachable_volumes, dtype=np.float64)


def ey_simulate(surfaces: FloatArray) -> FloatArray:
    k_reference = 0.25014
    extraction_limit = 0.3
    extraction_speed = 1.0 / surfaces
    extractions = extraction_speed / (k_reference + extraction_speed) * extraction_limit
    return np.asarray(extractions, dtype=np.float64)


def weighted_stddev(
    data: FloatArray,
    weights: FloatArray,
    frequency: bool = False,
    unbiased: bool = True,
) -> float:
    weights = weights.copy()
    if not np.nansum(weights):
        return float("nan")
    if unbiased is True:
        if frequency is True:
            bias_estimator = float((np.nansum(weights) - 1.0) / np.nansum(weights))
        else:
            bias_estimator = float(
                1.0 - np.nansum(weights**2) / np.nansum(weights) ** 2
            )
    else:
        bias_estimator = 1.0
    weights /= np.nansum(weights)
    wmean = np.nansum(data * weights)
    deviations = data - wmean
    if bias_estimator <= 0:
        return float("nan")
    wvar = np.nansum(deviations**2 * weights) / bias_estimator
    wstddev = np.sqrt(wvar)
    return float(wstddev)


def detect_particles(
    image: ImageArray,
    threshold: ThresholdResult,
    parameters: AnalysisParameters = DEFAULT_PARAMETERS,
    progress: Callable[[str], None] | None = None,
) -> DetectionResult:
    """Run the original four-neighbor, brightness-cost particle detector."""
    if image.ndim != 3 or image.shape[:2] != threshold.blue.shape:
        raise ValueError("Threshold result does not match the source image.")
    max_cluster_axis = parameters.max_cluster_axis
    min_surface = parameters.min_surface
    min_roundness_var = parameters.min_roundness
    reference_threshold = parameters.reference_threshold
    maxcost = parameters.maxcost
    sort_indices = np.argsort(threshold.blue[threshold.indices].astype(float))
    mask_threshold_sorted = (
        threshold.indices[0][sort_indices],
        threshold.indices[1][sort_indices],
    )
    X_mask = mask_threshold_sorted[0].astype(float)
    Y_mask = mask_threshold_sorted[1].astype(float)
    nmask = mask_threshold_sorted[0].size
    imdata_mask = threshold.blue[mask_threshold_sorted].astype(float)
    clusters: list[Cluster] = []
    counted = np.zeros(nmask, dtype=bool)
    for i in range(nmask):
        if progress is not None and i % 10 == 0:
            progress(
                f"Iteration #{i}; analyzed {min(np.sum(counted) / float(nmask) * 100, 99.9):.1f}%"
            )
        iopen = np.where(~counted)[0]
        if iopen.size == 0:
            break
        icurrent = iopen[0]
        dopen2 = (X_mask[icurrent] - X_mask[iopen]) ** 2 + (
            Y_mask[icurrent] - Y_mask[iopen]
        ) ** 2
        iwithinmax = np.where(dopen2 <= max_cluster_axis**2)
        if iwithinmax[0].size == 0:
            counted[icurrent] = True
            continue
        ipreclust = iopen[iwithinmax]
        qc_indices = quick_cluster(
            X_mask[ipreclust], Y_mask[ipreclust], X_mask[icurrent], Y_mask[icurrent]
        )
        iclust = ipreclust[qc_indices]
        if iclust.size < min_surface:
            counted[icurrent] = True
            continue
        if parameters.quick == 1:
            iclust_filtered = np.arange(iclust.size)
            maxcost_along_path = np.full(iclust.size, np.nan)
            cost = np.full(iclust.size, np.nan)
        else:
            dcurrent2 = (X_mask[iclust] - X_mask[icurrent]) ** 2 + (
                Y_mask[iclust] - Y_mask[icurrent]
            ) ** 2
            iclust = iclust[np.argsort(dcurrent2)]
            icurrent_in_clust = np.where(iclust == icurrent)
            if icurrent_in_clust[0].size != 1:
                raise ValueError(
                    "The starting pixel was not found in a cluster. This should never happen !"
                )
            cost = (
                imdata_mask[iclust] - imdata_mask[icurrent]
            ) ** 2 / threshold.background_median**2
            cost = np.maximum(cost, 0)
            iclust_filtered = np.copy(icurrent_in_clust[0])
            maxcost_along_path = np.full(iclust.size, np.nan)
            for ci in range(iclust.size):
                if iclust[ci] == icurrent:
                    continue
                idark_in_list = np.where(
                    imdata_mask[iclust[iclust_filtered]]
                    <= (threshold.background_median - imdata_mask[icurrent])
                    * reference_threshold
                    + imdata_mask[icurrent]
                )
                idark: Any = iclust[iclust_filtered[idark_in_list[0]]]
                if idark.size == 0:
                    raise ValueError(
                        "There should be at least one dark pixel in the cluster, this should never happen !"
                    )
                if idark.size > 1:
                    dist2 = (X_mask[idark] - X_mask[iclust[ci]]) ** 2 + (
                        Y_mask[idark] - Y_mask[iclust[ci]]
                    ) ** 2
                    idark = idark[np.argmin(dist2)]
                if iclust[ci] == idark:
                    maxcost_along_path[ci] = 0.0
                else:
                    x1 = X_mask[iclust[ci]]
                    y1 = Y_mask[iclust[ci]]
                    x2 = X_mask[idark]
                    y2 = Y_mask[idark]
                    x0 = X_mask[iclust]
                    y0 = Y_mask[iclust]
                    ddline = np.abs(
                        (y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1
                    ) / np.sqrt((y2 - y1) ** 2 + (x2 - x1) ** 2)
                    dd1 = np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
                    dd2 = np.sqrt((x2 - x0) ** 2 + (y2 - y0) ** 2)
                    dd12 = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                    ipath = np.where(
                        (ddline <= np.sqrt(2.0)) & (dd1 <= dd12) & (dd2 <= dd12)
                    )
                    ddonline = np.sqrt(dd2[ipath[0]] ** 2 - ddline[ipath[0]] ** 2)
                    ipath = ipath[0][np.argsort(ddonline)]
                    ddonline_sorted = np.sqrt(dd2[ipath] ** 2 - ddline[ipath] ** 2)
                    if np.diff(ddonline_sorted).max() > np.sqrt(2.0) * 1.01:
                        maxcost_along_path[ci] = None
                        continue
                    cost_path = cost[ipath]
                    if NSMOOTH < cost_path.size:
                        cost_path_sm = smooth(cost_path, NSMOOTH) * NSMOOTH
                    else:
                        cost_path_sm = np.full(cost_path.size, np.sum(cost_path))
                    maxcost_along_path[ci] = np.max(cost_path_sm)
                if maxcost_along_path[ci] < maxcost:
                    iclust_filtered = np.append(iclust_filtered, ci)
        counted[iclust] = True
        if iclust_filtered.size < min_surface:
            continue
        xlist = X_mask[iclust[iclust_filtered]]
        ylist = Y_mask[iclust[iclust_filtered]]
        zlist = imdata_mask[iclust[iclust_filtered]]
        if xlist.min() <= 0:
            continue
        if xlist.max() >= image.shape[0] - 1:
            continue
        if ylist.min() <= 0:
            continue
        if ylist.max() >= image.shape[1] - 1:
            continue
        if threshold.boundary_indices is not None:
            cluster_is_on_edge = False
            for ei in range(threshold.boundary_indices.size):
                x_edge_i = threshold.indices[0][threshold.boundary_indices[ei]]
                y_edge_i = threshold.indices[1][threshold.boundary_indices[ei]]
                found_on_edge = np.where((xlist == x_edge_i) & (ylist == y_edge_i))
                if found_on_edge[0].size != 0:
                    cluster_is_on_edge = True
                    break
            if cluster_is_on_edge:
                continue
        surface_multiplier = (
            threshold.background_median - zlist.min()
        ) / threshold.background_median
        surface_multiplier = np.maximum(surface_multiplier, 1.0)
        surface = float(iclust_filtered.size) * surface_multiplier
        xmean = np.mean(xlist)
        ymean = np.mean(ylist)
        dlist = np.sqrt((xlist - xmean) ** 2 + (ylist - ymean) ** 2)
        dlist = np.maximum(dlist, 0.0001)
        axis = np.max(dlist)
        if axis > max_cluster_axis:
            continue
        if surface == 1:
            roundness = 1.0
        else:
            roundness = float(surface) / (np.pi * float(axis) ** 2)
        if roundness < min_roundness_var:
            continue
        short_axis = surface / (np.pi * axis)
        volume = np.pi * short_axis**2 * axis
        clusteri_data: Cluster = {
            "CLUSTER_ID": i,
            "SURFACE": surface,
            "XLIST": xlist.astype(int),
            "YLIST": ylist.astype(int),
            "LONG_AXIS": axis,
            "ROUNDNESS": roundness,
            "VOLUME": volume,
            "SHORT_AXIS": short_axis,
            "XMEAN": xmean,
            "YMEAN": ymean,
            "XSTART": int(X_mask[icurrent]),
            "YSTART": int(Y_mask[icurrent]),
            "ZLIST": zlist,
            "ICLUST_FILTERED": iclust[iclust_filtered],
            "ICLUST": iclust,
            "MAXCOST_ALONG_PATH": maxcost_along_path,
            "COST": cost,
        }
        clusters.append(clusteri_data)
    return DetectionResult(clusters, measurements_from_clusters(clusters))
