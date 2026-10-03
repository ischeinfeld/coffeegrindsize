"""Headless test harness for the unmodified, pinned upstream routines.

Only class definitions are compiled; legacy imports and Tk startup never run.
The GUI collaborators are replaced by simple in-memory values for testing.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import matplotlib
import numpy as np
from matplotlib import path
from PIL import Image

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


class Value:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def legacy(image, *, quick=False, polygon=None, **options):
    source = Path(__file__).parent / "fixtures" / "legacy_reference.py"
    tree = ast.parse(source.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "coffeegrindsize_GUI")
    module = ast.Module(body=[cls], type_ignores=[])
    namespace = {
        "np": np, "Image": Image, "path": path, "plt": plt,
        "nsmooth": 3, "coffee_cell_size": 20., "default_log_binsize": .05,
        "default_binsize": .1, "threshold_image_display_name": "Thresholded",
        "outlines_image_display_name": "Cluster Outlines",
    }
    exec(compile(module, str(source), "exec"), namespace)
    obj = object.__new__(namespace["coffeegrindsize_GUI"])
    obj.master = SimpleNamespace(update=lambda: None)
    obj.redraw = lambda **kw: None
    obj.img_source = Image.fromarray(image)
    obj.img = obj.img_source
    obj.last_image_x = obj.last_image_y = 0
    obj.mask_threshold_edge = None
    obj.polygon_alpha = None if polygon is None else np.asarray(polygon)[:, 0]
    obj.polygon_beta = None if polygon is None else np.asarray(polygon)[:, 1]
    values = {
        "threshold_var": 58.8, "max_cluster_axis_var": 100.,
        "min_surface_var": 5., "min_roundness_var": 0.,
        "reference_threshold_var": .4, "maxcost_var": .35,
        "quick_var": int(quick), "pixel_scale_var": 10.,
        "histogram_type": "Available mass vs Surface", "data_label_var": "Test",
        "xlog_var": 1, "xaxis_auto_var": 1, "nbins_auto_var": 0,
        "nbins_var": 16, "xmin_var": .01, "xmax_var": 10.,
        "status_var": "", "display_type": "Original",
        "diam_average_var": "", "diam_stddev_var": "", "surf_average_var": "",
        "surf_stddev_var": "", "eff_var": "", "q_var": "",
    }
    values.update(options)
    for key, value in values.items():
        setattr(obj, key, Value(value))
    obj.threshold_image(None)
    obj.launch_psd(None)
    return obj


def synthetic_image():
    image = np.full((160, 200, 3), 245, dtype=np.uint8)
    rng = np.random.default_rng(19)
    for row, col, height, width in [(10, 10, 3, 3), (15, 45, 5, 6), (50, 15, 9, 12), (55, 70, 14, 16), (100, 110, 20, 27)]:
        values = rng.integers(15, 70, size=(height, width, 1), dtype=np.uint8)
        image[row:row+height, col:col+width] = values
    image[0:5, 150:155] = 20  # An edge particle must be rejected.
    image[140, 30] = 20  # An isolated pixel must be filtered.
    return image


def snapshot(obj):
    return {
        "mask": np.column_stack(obj.mask_threshold).tolist(),
        "clusters": [{key: np.asarray(cluster[key]).tolist() for key in ("SURFACE", "ROUNDNESS", "LONG_AXIS", "SHORT_AXIS", "VOLUME", "XLIST", "YLIST", "XMEAN", "YMEAN")} for cluster in obj.cluster_data],
        "statistics": {key: float(getattr(obj, key).get()) for key in ("diam_average_var", "diam_stddev_var", "surf_average_var", "surf_stddev_var", "eff_var", "q_var")},
    }
