import numpy as np
import pandas as pd
import pytest
from legacy import synthetic_image
from PIL import Image

from coffeegrindsize.core import detect_particles, prepare_histogram, threshold_image
from coffeegrindsize.io import (
    PARTICLE_COLUMNS,
    load_image,
    read_measurements,
    write_measurements,
)
from coffeegrindsize.models import HistogramOptions
from coffeegrindsize.plotting import render_histogram


@pytest.fixture
def measurements():
    image = synthetic_image()
    return detect_particles(image, threshold_image(image)).measurements


def test_legacy_csv_round_trip_and_statistics(tmp_path, measurements):
    destination = tmp_path / "sample_data.csv"
    stats_path = write_measurements(destination, measurements, 10)
    assert destination.read_text().splitlines()[0] == "ID," + ",".join(PARTICLE_COLUMNS)
    assert stats_path.name == "sample_data_stats.csv"
    assert (
        stats_path.read_text().splitlines()[0]
        == ",AVG_DIAM,STD_DIAM,AVG_SURF,STD_SURF,EFF,QUAL"
    )
    loaded, scale = read_measurements(destination)
    assert scale == 10
    for name in ("surface", "roundness", "short_axis", "long_axis", "volume"):
        np.testing.assert_allclose(
            getattr(loaded, name), getattr(measurements, name), rtol=1e-12
        )
    values = pd.read_csv(stats_path).iloc[0]
    assert values["AVG_DIAM"] == 2.16
    assert values["EFF"] == 55.4


def test_bad_csv(tmp_path, measurements):
    filename = tmp_path / "bad.csv"
    filename.write_text("SURFACE\n1\n")
    with pytest.raises(ValueError, match="Missing"):
        read_measurements(filename)
    write_measurements(filename, measurements, 10)
    frame = pd.read_csv(filename)
    frame.loc[0, "PIXEL_SCALE"] = 0
    frame.to_csv(filename, index=False)
    with pytest.raises(ValueError, match="positive"):
        read_measurements(filename)
    frame.loc[0, "PIXEL_SCALE"] = 20
    frame.to_csv(filename, index=False)
    with pytest.raises(ValueError, match="same"):
        read_measurements(filename)


@pytest.mark.parametrize("mode", ["L", "RGBA", "P"])
def test_image_modes_are_normalized(tmp_path, mode):
    filename = tmp_path / "image.png"
    Image.new(mode, (8, 8)).save(filename)
    assert load_image(filename).mode == "RGB"
    if mode == "RGBA":
        assert load_image(filename).getpixel((0, 0)) == (255, 255, 255)


def test_unsupported_image_mode(tmp_path):
    filename = tmp_path / "16bit.png"
    Image.new("I;16", (8, 8)).save(filename)
    with pytest.raises(ValueError, match="8-bit"):
        load_image(filename)


@pytest.mark.parametrize("size", [(752, 718), (1000, 600), (1504, 1436)])
def test_plot_dimensions_and_comparison(size, measurements):
    options = HistogramOptions(bin_count=16)
    primary = prepare_histogram(measurements, 10, options)
    comparison = prepare_histogram(measurements, 10, options, primary.edges)
    image = render_histogram(
        primary, width=size[0], height=size[1], comparison=comparison
    )
    assert image.size == size
    assert image.mode == "RGB"
    assert np.asarray(image).std() > 0
