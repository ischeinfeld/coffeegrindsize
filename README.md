# coffeegrindsize

[![macOS checks](https://github.com/ischeinfeld/coffeegrindsize/actions/workflows/macos.yml/badge.svg)](https://github.com/ischeinfeld/coffeegrindsize/actions/workflows/macos.yml)

Analyze coffee particle size distributions from photographs on your own computer.
This MIT-licensed fork modernizes Jonathan Gagné's Tkinter application and retains
Chris Satterlee's installer-tooling history. Development starts at `1.1.0.dev0`.
The detector, defaults, pixel measurements, and scientific formulas are preserved.

## macOS development setup

Use standard CPython 3.14 with its matching Tk package. Installing a Python
package named `tk` does not install Tkinter. Homebrew's Python is required here
because a Python downloaded automatically by uv may lack Tk.

```sh
brew install uv python@3.14 python-tk@3.14
git clone --filter=blob:none https://github.com/ischeinfeld/coffeegrindsize.git
cd coffeegrindsize
"$(brew --prefix python@3.14)/bin/python3.14" -c 'import tkinter; root = tkinter.Tk(); root.destroy()'
uv venv --python "$(brew --prefix python@3.14)/bin/python3.14"
uv sync --locked
uv run coffeegrindsize
```

The Homebrew prefix is detected automatically on Apple Silicon and Intel Macs.
`uv run python -m coffeegrindsize` provides the same entry point. Imports do not
open a window. To diagnose Tk startup, run `uv run python -m tkinter`.
The committed `uv.lock` fixes application and development dependencies.

## Using the app

1. **Open Image**: use a well-lit photograph of separated grounds on a light
   background, with a ruler or known reference object in the same plane.
   The original `Help/Better_Example_Picture.png` and
   `Help/Decent_Example_Picture.png` are included. Large or noisy images can take
   a long time; use **Reduce Image Quality** or a small analysis region first.
2. **Calibrate**: click **Select Reference Object**, click one end of the
   reference, move the red measuring line to the other end, and click again.
   Choose the object from **Reference Object**, or enter its known size in
   **Reference Physical Size** in mm. Pixel scale is pixels/mm and must be
   positive. Recalibrate after reducing image quality in simple mode.
3. **Select Analysis Region**: click corners around the grounds, excluding the
   reference and shadows; press Return or Escape to close the polygon. At least
   three corners are required. Particles touching image or region edges are
   excluded by the legacy detector.
4. **Threshold Image**, then **Launch Particle Detection**. Inspect the red
   outlines and blue centers. **Erase Clusters** removes particles within the
   cursor circle; zoom changes its precision. Press Escape to leave erase mode.
5. **Create Histogram**: choose a histogram type, label, and legend position.
   Use **Display Type** to return to the original, threshold, or outlines view.
6. **Save Data** writes particle measurements and an adjacent `_stats.csv`.
   **Save View** saves the currently displayed image as PNG. **Load Data**
   reloads a particle CSV; **Load Comparison Data** overlays another dataset
   using the current histogram's bin edges. **Flush Comparison Data** clears it.

The **File → Turn Expert Mode On/Off** menu exposes detection thresholds,
filters, quick detection, and histogram ranges and bin counts. Quick detection
can intentionally produce different measurements from full detection.
In expert mode, output uses the selected directory and session name without a
save dialog. **Reset All Parameters** restores defaults; **Reboot** starts a
fresh session within the same application.

For a fast practice workflow, open `tests/fixtures/decent_crop.png`, enter
`10` directly in **Pixel Scale**, then threshold and detect.
The default full detector finds 7 particles. These calibration values are an
arbitrary test scale, not the actual scale of the photographed grounds.
Export, reload, and compare the same file to exercise the entire workflow.

## CSV compatibility and numerical model

Particle CSV columns retain their order:
`ID,SURFACE,ROUNDNESS,SHORT_AXIS,LONG_AXIS,VOLUME,PIXEL_SCALE`.
Surface is in pixels², axis lengths use the original semi-axis convention in
pixels, volume is in pixels³, roundness is dimensionless, and pixel scale is
pixels/mm. Histogram axes convert to mm, mm², or mm³. Statistics retain
`AVG_DIAM,STD_DIAM,AVG_SURF,STD_SURF,EFF,QUAL`, their legacy rounding, and the
unnamed index column. Diameter/surface statistics are mass weighted using the
original accessible-mass model; efficiency and quality are model estimates.

See [provenance and compatibility notes](docs/UPSTREAM.md) for pinned source
revisions, historical manuals, and documented behavior on previously undefined
inputs. Matching legacy results is not independent scientific validation.

## Hacking and verification

Editable installation means changes in `src/coffeegrindsize/` take effect on the
next launch. `app.py` owns Tk widgets; `core.py` owns numerical operations;
`models.py` defines typed inputs/results; `io.py` and `plotting.py` handle files
and Agg rendering without Tk. The UI retains much of the original layout and
can be split into smaller views in subsequent work.

```python
import numpy as np
from coffeegrindsize.core import detect_particles, threshold_image
from coffeegrindsize.io import load_image
from coffeegrindsize.models import AnalysisParameters

image = np.asarray(load_image("tests/fixtures/decent_crop.png"))
parameters = AnalysisParameters()
threshold = threshold_image(image, parameters)
result = detect_particles(image, threshold, parameters)
print(result.measurements.count)  # 7
```

Core polygons use `(column, row)` coordinates; threshold indices and the
legacy cluster `XLIST`/`YLIST` use `(row, column)`. Measurement arrays retain
pixel units until an explicit calibration is supplied.

```sh
uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run mypy src/coffeegrindsize/core.py src/coffeegrindsize/models.py src/coffeegrindsize/io.py src/coffeegrindsize/plotting.py
uv run pytest -m 'not gui'
COFFEEGRINDSIZE_GUI_TESTS=1 uv run pytest
uv build
```

GUI tests require a working Mac desktop/Tk display. They create real Tk windows
and drive callbacks, substituting temporary paths for file dialogs. macOS CI
runs the locked install, lint/format checks, strict core type checks, numerical
regressions, GUI workflows/startup/shutdown, and a wheel build.

`tests/fixtures/legacy_reference.py` is the unchanged 2019 application, retained
only as a regression oracle. The test harness extracts its class without
starting Tk. `tools/capture_baseline.py` reproduces the recorded memberships,
measurements, and rounded statistics. Counts/memberships must match exactly;
floating-point comparisons use `rtol=1e-10, atol=1e-12` (histogram error estimates
use `rtol=1e-7, atol=1e-12`). Review scientific changes separately from refactors.

The local remotes are `origin` (this fork), `upstream` (Jonathan Gagné), and
`csatt` (historical packaging). `main` is maintained; `master` preserves the
original branch. History has not been rewritten. Partial clones avoid fetching
the historical bundled applications until those revisions are inspected.

## Current scope

Mac development is supported first. Detection remains synchronous and may be
slow on noisy photographs; conflicting controls are disabled while it runs.
Cancellation, algorithm optimization, revised volume formulas, new installers,
signing/notarization, and Windows/Linux certification are deferred.
`build_tools/` is historical reference, not the supported build path. The old
[v1.0.0 installers](https://github.com/csatt/coffeegrindsize/releases/tag/v1.0.0)
contain the legacy application, not this development version.

Report problems or propose changes in [this fork's issue tracker](https://github.com/ischeinfeld/coffeegrindsize/issues).
