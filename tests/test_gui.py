import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from legacy import synthetic_image
from PIL import Image

pytestmark = pytest.mark.gui


@pytest.fixture
def app():
    if os.environ.get("COFFEEGRINDSIZE_GUI_TESTS") != "1":
        pytest.skip("Set COFFEEGRINDSIZE_GUI_TESTS=1 with a working Tk display")
    import tkinter as tk

    from coffeegrindsize.app import CoffeeGrindSizeApp

    root = tk.Tk()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    application = CoffeeGrindSizeApp(root)
    yield application
    try:
        root.update()
        root.destroy()
    except tk.TclError:
        pass
    assert not errors


def open_synthetic(app, tmp_path, monkeypatch):
    filename = tmp_path / "particles.png"
    Image.fromarray(synthetic_image()).save(filename)
    monkeypatch.setattr(
        "coffeegrindsize.app.filedialog.askopenfilename", lambda **kw: str(filename)
    )
    app.open_image()
    app.pixel_length_var.set("100")
    app.physical_length_var.set("10")
    assert app.pixel_scale_var.get() == "10.000"
    return filename


def test_full_gui_workflow(app, tmp_path, monkeypatch):
    open_synthetic(app, tmp_path, monkeypatch)
    app.threshold_image()
    app.launch_psd()
    assert app.nclusters == 5
    assert app.img_clusters is not None
    assert app.diam_average_var.get() == "2.16"
    app.create_histogram()
    assert app.img_histogram.size == (app.canvas_width, app.canvas_height)
    destination = tmp_path / "particles_data.csv"
    monkeypatch.setattr(
        "coffeegrindsize.app.filedialog.asksaveasfilename",
        lambda **kw: str(destination),
    )
    app.save_data()
    assert destination.exists()
    monkeypatch.setattr(
        "coffeegrindsize.app.filedialog.askopenfilename", lambda **kw: str(destination)
    )
    app.load_comparison_data()
    assert app.comparison.nclusters == 5
    app.load_data()
    assert app.nclusters == 5
    app.flush_comparison_data()
    assert app.comparison.nclusters is None
    view = tmp_path / "view.png"
    monkeypatch.setattr(
        "coffeegrindsize.app.filedialog.asksaveasfilename", lambda **kw: str(view)
    )
    app.save_histogram(None)
    assert Image.open(view).size == app.img_histogram.size


def test_dialog_cancellation_preserves_state(app, tmp_path, monkeypatch):
    open_synthetic(app, tmp_path, monkeypatch)
    app.threshold_image()
    app.launch_psd()
    before = app.img_source
    monkeypatch.setattr(
        "coffeegrindsize.app.filedialog.askopenfilename", lambda **kw: ""
    )
    monkeypatch.setattr(
        "coffeegrindsize.app.filedialog.asksaveasfilename", lambda **kw: ""
    )
    monkeypatch.setattr("coffeegrindsize.app.filedialog.askdirectory", lambda **kw: "")
    old_directory = app.output_dir
    app.open_image()
    app.load_data()
    app.load_comparison_data()
    app.save_data()
    app.save_histogram(None)
    app.select_output_dir()
    assert app.img_source is before
    assert app.nclusters == 5
    assert app.output_dir == old_directory


def test_zoom_downsampling_reset_and_busy_guard(app, tmp_path, monkeypatch):
    open_synthetic(app, tmp_path, monkeypatch)
    original_scale = app.scale
    app.zoom_in_button()
    assert app.scale == original_scale * 2
    app.zoom_out_button()
    assert app.scale == original_scale
    app.threshold_image()
    app.launch_psd()
    app.erase_clusters(None)
    app.zoom_in_button()  # No event object exists for a button callback.
    assert app.erase_clusters_mode
    app._busy = True
    app.reset_gui()
    app.open_image()
    assert app.nclusters == 5
    app._busy = False
    app.downsample_image()
    assert app.img_source.size == (100, 80)
    assert app.nclusters is None and app._threshold is None
    app.reset_gui()
    assert app.img_source is None
    app.reset_status()
    app.reset_zoom()


def test_calibration_selection_region_and_cluster_editing(app, tmp_path, monkeypatch):
    open_synthetic(app, tmp_path, monkeypatch)
    app.line_start(SimpleNamespace(x=100, y=100))
    app.line_move(SimpleNamespace(x=100 + app.scale * 100, y=100))
    assert float(app.pixel_length_var.get()) == 100
    assert app.pixel_scale_var.get() == "10.000"
    app.select_region(None)
    for x, y in [(5, 5), (90, 5), (90, 90), (5, 90)]:
        center_x, center_y = app.image_canvas.coords(app.image_id)
        app.mouse_x = center_x - app.image_canvas.canvasx(0) + (x - 100) * app.scale
        app.mouse_y = center_y - app.image_canvas.canvasy(0) + (y - 80) * app.scale
        app.move_start(SimpleNamespace(x=app.mouse_x, y=app.mouse_y))
    app.quit_region_select(None)
    np.testing.assert_allclose(app.polygon_alpha, [5, 90, 90, 5, 5])
    app.threshold_image()
    app.launch_psd()
    assert app.nclusters == 4  # Region excludes the large particle at (110, 100).
    app.create_histogram()
    app.display_type.set("Cluster Outlines")
    app.change_display_type()
    assert app.scale == app.original_scale
    app.erase_clusters(None)
    first = app.cluster_data[0]
    center_x, center_y = app.image_canvas.coords(app.image_id)
    app.mouse_x = (
        center_x - app.image_canvas.canvasx(0) + (first["YMEAN"] - 100) * app.scale
    )
    app.mouse_y = (
        center_y - app.image_canvas.canvasy(0) + (first["XMEAN"] - 80) * app.scale
    )
    app.move_start(SimpleNamespace(x=int(app.mouse_x), y=int(app.mouse_y)))
    assert app.nclusters == 3
    assert app.img_histogram is None
    app.quit_region_select(None)
    app.toggle_expert_mode()
    assert app.expert_mode
    app.xaxis_auto_var.set(0)
    app.xaxis_auto_event()
    app.nbins_auto_var.set(0)
    app.nbins_auto_event()
    app.pixel_scale_var.set("10")
    app.downsample_image()
    assert float(app.pixel_scale_var.get()) == 5
    app.toggle_expert_mode()
    assert not app.expert_mode


def test_invalid_and_empty_inputs_do_not_crash(app, tmp_path, monkeypatch):
    open_synthetic(app, tmp_path, monkeypatch)
    app.physical_length_var.set("0")
    assert app.pixel_scale_var.get() == "None"
    app.threshold_image()
    app.launch_psd()
    app.create_histogram()
    assert app.img_histogram is None
    app.img_source = Image.fromarray(np.full((20, 20, 3), 255, dtype=np.uint8))
    app.threshold_image()
    app.launch_psd()
    assert app.nclusters == 0
    app.create_histogram()
    app.save_data()


def test_real_photo_crop_workflow(app, monkeypatch):
    filename = Path(__file__).parent / "fixtures" / "decent_crop.png"
    monkeypatch.setattr(
        "coffeegrindsize.app.filedialog.askopenfilename", lambda **kw: str(filename)
    )
    app.open_image()
    app.pixel_length_var.set("100")
    app.physical_length_var.set("10")
    app.threshold_image()
    app.launch_psd()
    assert app.nclusters == 7
    app.create_histogram()
    assert app.img_histogram is not None


def test_module_import_and_entrypoint(monkeypatch):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import coffeegrindsize; import sys; assert 'tkinter' not in sys.modules; print(coffeegrindsize.__version__)",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == "1.1.0.dev0"


def test_entrypoint_startup_and_shutdown(app, monkeypatch):
    from importlib.metadata import entry_points

    from coffeegrindsize import app as app_module

    app.master.after(50, app.master.destroy)
    monkeypatch.setattr(app_module.tk, "Tk", lambda: app.master)
    entrypoint = next(
        iter(entry_points(group="console_scripts", name="coffeegrindsize"))
    )
    assert entrypoint.load() is app_module.main
    app_module.main()
