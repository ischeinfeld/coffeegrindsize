import hashlib
import json
import warnings
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from legacy import legacy, plt, synthetic_image
from PIL import Image

from coffeegrindsize.core import (
    calculate_statistics,
    detect_particles,
    prepare_histogram,
    threshold_image,
    weighted_stddev,
)
from coffeegrindsize.models import (
    HISTOGRAM_KINDS,
    AnalysisParameters,
    HistogramOptions,
    validate_scale,
)

FIXTURES = Path(__file__).parent / "fixtures"
BASELINE = json.loads((FIXTURES / "baseline.json").read_text())


def test_legacy_oracle_is_unchanged():
    assert hashlib.sha256(
        (FIXTURES / "legacy_reference.py").read_bytes()
    ).hexdigest() == (
        "7f3445b05a46be7105bafd843e3cc38f52a4c9f9c76d44ed835b92c54eb018ec"
    )


def image_named(name):
    if name == "synthetic":
        return synthetic_image()
    with Image.open(FIXTURES / f"{name}_crop.png") as image:
        return np.asarray(image)


def analyze(image, parameters=None, polygon=None):
    if parameters is None:
        parameters = AnalysisParameters()
    threshold = threshold_image(image, parameters, polygon)
    return threshold, detect_particles(image, threshold, parameters)


@pytest.mark.parametrize("name", ["synthetic", "better", "decent"])
@pytest.mark.parametrize("quick", [False, True])
def test_captured_legacy_detector_and_statistics(name, quick):
    threshold, result = analyze(image_named(name), AnalysisParameters(quick=quick))
    expected = BASELINE[f"{name}_{'quick' if quick else 'full'}"]
    np.testing.assert_array_equal(np.column_stack(threshold.indices), expected["mask"])
    assert len(result.clusters) == len(expected["clusters"])
    for actual, reference in zip(result.clusters, expected["clusters"], strict=True):
        for key, value in reference.items():
            if key in ("XLIST", "YLIST"):
                np.testing.assert_array_equal(actual[key], value)
            else:
                np.testing.assert_allclose(actual[key], value, rtol=1e-10, atol=1e-12)
    values = calculate_statistics(result.measurements, 10).legacy_values()
    for new, old in zip(values.values(), expected["statistics"].values(), strict=True):
        assert new == old


@pytest.mark.parametrize("quick", [False, True])
@pytest.mark.parametrize(
    "overrides", [{"min_surface": 40}, {"min_roundness": 0.9}, {"max_cluster_axis": 7}]
)
def test_region_and_filter_parity(quick, overrides):
    polygon = np.array([(5, 5), (90, 5), (90, 90), (5, 90), (5, 5)], dtype=float)
    image = synthetic_image()
    _, result = analyze(image, AnalysisParameters(quick=quick, **overrides), polygon)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        reference = legacy(
            image,
            quick=quick,
            polygon=polygon,
            **{key + "_var": value for key, value in overrides.items()},
        )
    assert len(result.clusters) == len(reference.cluster_data)
    for actual, old in zip(result.clusters, reference.cluster_data, strict=True):
        np.testing.assert_array_equal(actual["XLIST"], old["XLIST"])
        np.testing.assert_array_equal(actual["YLIST"], old["YLIST"])
        assert actual["VOLUME"] == old["VOLUME"]


@pytest.fixture(scope="module")
def legacy_synthetic():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return legacy(synthetic_image())


@pytest.mark.parametrize("kind", HISTOGRAM_KINDS)
@pytest.mark.parametrize("log", [False, True])
@pytest.mark.parametrize("auto_bins", [False, True])
def test_histogram_data_and_error_estimates_match_legacy(
    kind, log, auto_bins, legacy_synthetic
):
    _, result = analyze(synthetic_image())
    obj = legacy_synthetic
    obj.histogram_type.set(kind)
    obj.xlog_var.set(int(log))
    obj.nbins_auto_var.set(int(auto_bins))
    options = HistogramOptions(kind=kind, log=log, bin_count=None if auto_bins else 16)
    actual = prepare_histogram(result.measurements, 10, options)
    fig = plt.figure()
    try:
        with (
            warnings.catch_warnings(),
            patch.object(plt, "hist", wraps=plt.hist) as hist,
            patch.object(plt, "errorbar", wraps=plt.errorbar) as errorbar,
        ):
            warnings.simplefilter("ignore", RuntimeWarning)
            expected_edges, _ = obj.psd_hist_from_data(obj)
            expected_values, _ = np.histogram(
                hist.call_args.args[0],
                bins=expected_edges,
                weights=hist.call_args.kwargs["weights"],
            )
        np.testing.assert_allclose(actual.edges, expected_edges, rtol=1e-10, atol=1e-12)
        np.testing.assert_allclose(
            actual.values, expected_values, rtol=1e-10, atol=1e-12
        )
        np.testing.assert_allclose(
            np.array([actual.poisson_negative, actual.poisson_positive]),
            errorbar.call_args_list[0].kwargs["yerr"],
            rtol=1e-7,
            atol=1e-12,
            equal_nan=True,
        )
        np.testing.assert_allclose(actual.average, errorbar.call_args_list[-1].args[0])
        np.testing.assert_allclose(
            np.array([actual.average_negative, actual.average_positive]).reshape(2, 1),
            errorbar.call_args_list[-1].kwargs["xerr"],
            rtol=1e-7,
            atol=1e-12,
            equal_nan=True,
        )
    finally:
        plt.close(fig)


@pytest.mark.parametrize("scale", [0, -1, float("nan"), float("inf")])
def test_invalid_calibration(scale):
    with pytest.raises(ValueError, match="positive"):
        validate_scale(scale)


def test_empty_image_result_and_outside_region():
    white = np.full((20, 20, 3), 255, dtype=np.uint8)
    _, empty = analyze(white)
    assert empty.measurements.count == 0
    with pytest.raises(ValueError, match="No particles"):
        prepare_histogram(empty.measurements, 10)
    with pytest.raises(ValueError, match="No image pixels"):
        threshold_image(
            white, polygon=np.array([(30, 30), (40, 30), (40, 40)], dtype=float)
        )


def test_single_particle_and_constant_histogram():
    image = np.full((30, 30, 3), 255, dtype=np.uint8)
    image[10:15, 10:15] = 20
    _, result = analyze(image)
    assert result.measurements.count == 1
    histogram = prepare_histogram(result.measurements, 10)
    assert histogram.values.sum() == pytest.approx(1)
    assert histogram.average_negative == histogram.average_positive == 0


def test_bad_image_and_parameters():
    with pytest.raises(ValueError, match="RGB"):
        threshold_image(np.zeros((10, 10), dtype=np.uint8))
    with pytest.raises(ValueError):
        AnalysisParameters(threshold=float("nan"))
    with pytest.raises(ValueError):
        HistogramOptions(log=True, auto_range=False, minimum=0)


def test_calibration_scales_dimensions_and_manual_range():
    _, result = analyze(synthetic_image())
    first = calculate_statistics(result.measurements, 10)
    second = calculate_statistics(result.measurements, 20)
    # Reweighting depends on physical size; test direct dimensions via histograms.
    options = HistogramOptions(kind="Number vs Diameter", bin_count=16)
    one = prepare_histogram(result.measurements, 10, options)
    two = prepare_histogram(result.measurements, 20, options)
    np.testing.assert_allclose(one.edges, two.edges * 2)
    assert first.average_diameter > second.average_diameter
    manual = prepare_histogram(
        result.measurements,
        10,
        HistogramOptions(
            kind="Number vs Diameter",
            log=False,
            auto_range=False,
            minimum=0.1,
            maximum=4,
            bin_count=10,
        ),
    )
    assert manual.edges[0] == 0.1 and manual.edges[-1] == 4
    with pytest.raises(ValueError, match="no particles"):
        prepare_histogram(
            result.measurements,
            10,
            HistogramOptions(log=False, auto_range=False, minimum=100, maximum=200),
        )


def test_weighted_stddev_does_not_modify_input():
    weights = np.array([2.0, 3.0, 4.0])
    before = weights.copy()
    assert np.isfinite(weighted_stddev(np.array([1.0, 2.0, 3.0]), weights))
    np.testing.assert_array_equal(weights, before)
