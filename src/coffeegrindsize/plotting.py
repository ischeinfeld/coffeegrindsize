"""Render histograms through an explicit Agg canvas, including on Retina Macs."""

import numpy as np
from matplotlib import ticker
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.legend import Legend
from PIL import Image

from .models import Histogram


def render_histogram(
    primary: Histogram,
    *,
    width: int = 1000,
    height: int = 600,
    log: bool = True,
    label: str = "Current Data",
    comparison: Histogram | None = None,
    comparison_label: str = "Comparison Data",
    legend: str = "best",
) -> Image.Image:
    """Return a standalone RGB image without Tk or pyplot global state."""
    if width <= 0 or height <= 0:
        raise ValueError("Plot dimensions must be positive.")
    figure = Figure(figsize=(width / 192, height / 192), dpi=192)
    canvas = FigureCanvasAgg(figure)
    axes = figure.add_subplot(111)
    for spine in axes.spines.values():
        spine.set_linewidth(2)
    height_reference = float(np.nanmax(primary.values) * 0.05)

    def draw(
        hist: Histogram, color: tuple[float, float, float], name: str, compare: bool
    ) -> None:
        if compare:
            axes.stairs(hist.values, hist.edges, label=name, color=color, linewidth=2)
        else:
            axes.bar(
                hist.centers,
                hist.values,
                width=np.diff(hist.edges) * 0.8,
                label=name,
                color=color,
                linewidth=2,
            )
        shift = 0.1 if compare else (-0.1 if comparison is not None else 0)
        positions = (
            hist.centers * (hist.centers / hist.edges[:-1]) ** shift
            if log
            else hist.centers + (hist.centers - hist.edges[:-1]) * shift
        )
        axes.errorbar(
            positions,
            hist.values,
            yerr=np.array([hist.poisson_negative, hist.poisson_positive]),
            linestyle="",
            color=tuple(c / 2 for c in color),
            elinewidth=2,
            alpha=0.8,
            zorder=15,
        )
        xerr = np.array([hist.average_negative, hist.average_positive]).reshape(2, 1)
        ypos = height_reference * (2 if compare else 1)
        axes.errorbar(
            hist.average,
            ypos,
            xerr=xerr,
            marker="o",
            markersize=11.2,
            linestyle="",
            color="white",
            elinewidth=4,
            capsize=4,
            capthick=3,
            zorder=19,
        )
        axes.errorbar(
            hist.average,
            ypos,
            xerr=xerr,
            marker="o",
            markersize=8,
            linestyle="",
            color=color,
            ecolor=(
                color[0] + (1 - color[0]) * 0.3,
                color[1] + (1 - color[1]) * 0.3,
                color[2] + (1 - color[2]) * 0.3,
            ),
            markeredgewidth=1.5,
            markeredgecolor="k",
            elinewidth=2,
            capsize=3,
            capthick=2,
            zorder=20,
        )

    draw(primary, (147 / 255, 36 / 255, 30 / 255), label, False)
    if comparison is not None:
        draw(comparison, (74 / 255, 124 / 255, 179 / 255), comparison_label, True)
    if log:
        axes.set_xscale("log")
        axes.xaxis.set_minor_formatter(ticker.LogFormatter())
        axes.xaxis.set_major_formatter(ticker.ScalarFormatter())
    axes.set_xlabel(primary.xlabel, fontsize=16)
    axes.set_ylabel(primary.ylabel, fontsize=16)
    if legend.lower() not in Legend.codes:
        raise ValueError("Unknown legend position: " + legend)
    axes.legend(loc=Legend.codes[legend.lower()])
    _style_ticks(axes)
    figure.tight_layout()
    canvas.draw()  # type: ignore[no-untyped-call]  # Matplotlib Agg stubs lack these signatures.
    # Buffer shape comes from the renderer, not a logical Tk window size.
    rgba = canvas.buffer_rgba()  # type: ignore[no-untyped-call]
    return Image.fromarray(np.asarray(rgba)[:, :, :3].copy())


def _style_ticks(axes: Axes) -> None:
    axes.tick_params(axis="both", which="major", labelsize=8, length=5, width=2)
    axes.tick_params(axis="both", which="minor", length=4, width=1)
