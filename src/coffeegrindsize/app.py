"""Tkinter desktop UI. Numerical analysis lives in core.py."""

from __future__ import annotations

import logging
import os
import time
import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from tkinter import filedialog
from types import SimpleNamespace
from typing import Any

import numpy as np
from PIL import Image, ImageTk

from .core import (
    calculate_statistics,
    detect_particles,
    measurements_from_clusters,
    prepare_histogram,
    threshold_image,
)
from .io import load_image, read_measurements, write_measurements
from .models import AnalysisParameters, HistogramOptions, Measurements, validate_scale
from .plotting import render_histogram


def guard_action(function: Callable[..., Any]) -> Callable[..., Any]:
    """Reject reentrant actions and report recoverable input/file errors."""

    @wraps(function)
    def guarded(self: CoffeeGrindSizeApp, *args: Any, **kwargs: Any) -> Any:
        if self._busy:
            return None
        try:
            return function(self, *args, **kwargs)
        except (ValueError, TypeError, OSError) as error:
            logging.getLogger(__name__).debug("Application input error", exc_info=True)
            self.status_var.set(str(error))
            return None

    return guarded


@dataclass
class ComparisonState:
    pixel_scale_var: tk.StringVar
    nclusters: int | None = None
    clusters_surface: Any = None
    clusters_roundness: Any = None
    clusters_short_axis: Any = None
    clusters_long_axis: Any = None
    clusters_volume: Any = None


def_display_advanced_options = False
def_expert_mode = False
def_reference_threshold = 0.4
nsmooth = 3
def_maxcost = 0.35
def_threshold = 58.8
def_pixel_scale = None
def_max_cluster_axis = 100
def_min_surface = 5
def_min_roundness = 0
def_min_x_axis = 0.01
def_max_x_axis = 10
coffee_cell_size = 20.0
def_session_name = "PSD_" + time.strftime("%Y%m%d_%Hh%Mm%Ss")
original_image_display_name = "Original"
threshold_image_display_name = "Thresholded"
outlines_image_display_name = "Cluster Outlines"
histogram_image_display_name = "Histograms"
default_log_binsize = 0.05
default_binsize = 0.1
reference_objects_dict = {
    "Custom": None,
    "Canadian Quarter": 23.81,
    "Canadian Dollar": 26.5,
    "Canadian Dime": 18.03,
    "Canadian Two Dollars": 28.0,
    "Canadian Five Cents": 21.3,
    "US Quarter": 24.26,
    "US Dollar": 26.92,
    "US Dime": 17.91,
    "US Penny": 19.05,
    "2 Euros": 25.75,
    "1 Euro": 23.25,
    "50 Euro Cents": 24.25,
    "20 Euro Cents": 22.25,
}
def_output_dir = os.path.expanduser("~")


class CoffeeGrindSizeApp:
    def __init__(self, root: tk.Tk) -> None:
        self._busy = False
        self._threshold = None
        self.output_dir = def_output_dir
        self.expert_mode = def_expert_mode
        self.image_id = None
        self.nclusters = None
        self.comparison = ComparisonState(
            pixel_scale_var=tk.StringVar(root, value="None")
        )
        self.mouse_click_mode = None
        self.img = None
        self.img_source = None
        self.img_threshold = None
        self.img_clusters = None
        self.img_histogram = None
        self.linex_start = None
        self.liney_start = None
        self.line_obj = None
        self.polygon_alpha = None
        self.polygon_beta = None
        self.selreg_current_line = None
        self.cursor_text = None
        self._threshold = None
        self.mask_threshold = None
        self.mask_threshold_edge = None
        self.cluster_data = None
        self.scale = 1.0
        self.original_scale = 1.0
        self.max_scale = 8.0
        self.zoom_dir = 0
        self.master = root
        self.options_row = 1
        self.simple_options_row = 1
        self.width_entries = 6
        self.title_padx = 12
        self.toolbar_padx = 6
        self.toolbar_pady = 0
        self.canvas_width = min(1000, max(320, self.master.winfo_screenwidth() - 760))
        self.canvas_height = max(300, int(self.master.winfo_screenheight() * 0.9 - 165))
        self.last_image_x = self.canvas_width / 2
        self.last_image_y = self.canvas_height / 2
        self.mouse_x, self.mouse_y = self.last_image_x, self.last_image_y
        self.erase_clusters_mode = False
        self.erase_circle_radius = 20
        self.erasemode_current_circle = None
        self.display_advanced_options = def_display_advanced_options
        self.reference_threshold_var = None
        self.maxcost_var = None
        self.master.title(
            "Coffee Particle Size Distribution — Jonathan Gagné / ischeinfeld"
        )
        toolbar_bg = "gray90"
        toolbar = tk.Frame(self.master, bg=toolbar_bg)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        toolbar2 = tk.Frame(self.master, bg=toolbar_bg)
        toolbar2.pack(side=tk.TOP, fill=tk.X)
        self.status_var = tk.StringVar(self.master)
        self.status_var.set("Idle...")
        status = tk.Label(
            self.master,
            textvariable=self.status_var,
            anchor=tk.W,
            bg="grey",
            relief=tk.SUNKEN,
        )
        status.pack(side=tk.BOTTOM, fill=tk.X)
        self.container_options = tk.Frame(root, width=720)
        self.container_options.pack(side="left", fill=tk.Y)
        options_width = 500
        self.frame_options = tk.Frame(self.container_options, width=options_width)
        self.frame_options.grid(
            row=0, column=0, sticky="nsew", columnspan=1, rowspan=25
        )
        self.simple_frame_options = tk.Frame(
            self.container_options, width=options_width
        )
        self.simple_frame_options.grid(
            row=0, column=0, sticky="nsew", columnspan=1, rowspan=25
        )
        self.label_title("Physical Scale of the Image:")
        if def_pixel_scale is None:
            def_pix_len = None
        else:
            def_pix_len = def_pixel_scale * float(reference_objects_dict["Custom"])
        self.pixel_length_var, self.pixel_length_id, self.simple_pixel_length_id = (
            self.label_entry(
                def_pix_len,
                "Reference Pixel Length:",
                "pix",
                entry_id=True,
                clear_on_click=True,
            )
        )
        (
            self.physical_length_var,
            self.physical_length_id,
            self.simple_physical_length_id,
        ) = self.label_entry(
            reference_objects_dict["Custom"],
            "Reference Physical Size:",
            "mm",
            entry_id=True,
            event_on_entry="update_pixel_scale",
            clear_on_click=True,
        )
        self.pixel_length_id.config(state=tk.DISABLED)
        self.simple_pixel_length_id.config(state=tk.DISABLED)
        self.physical_angle_var = tk.StringVar(self.master)
        self.reference_object = self.dropdown_entry(
            "Reference Object:",
            list(reference_objects_dict.keys()),
            self.change_reference_object,
        )
        self.pixel_scale_var = self.label_entry(
            def_pixel_scale,
            "Pixel Scale:",
            "pix/mm",
            clear_on_click=True,
            event_on_entry="update_statistics",
        )
        self.label_title("Threshold Step:", advanced=True)
        self.threshold_var = self.label_entry(
            def_threshold, "Threshold:", "%", advanced=True, clear_on_click=True
        )
        self.label_title("Particle Detection Step:", advanced=True)
        self.max_cluster_axis_var = self.label_entry(
            def_max_cluster_axis,
            "Maximum Cluster Diameter:",
            "pix",
            advanced=True,
            clear_on_click=True,
        )
        self.min_surface_var = self.label_entry(
            def_min_surface,
            "Minimum Cluster Surface:",
            "pix²",
            advanced=True,
            clear_on_click=True,
        )
        self.min_roundness_var = self.label_entry(
            def_min_roundness,
            "Minimum Roundness:",
            "",
            advanced=True,
            clear_on_click=True,
        )
        if self.display_advanced_options is True:
            self.reference_threshold_var = self.label_entry(
                def_reference_threshold, "Ref. Threshold:", "", advanced=True
            )
        elif self.reference_threshold_var is None:
            self.reference_threshold_var = tk.StringVar(self.master)
            self.reference_threshold_var.set(str(def_reference_threshold))
        if self.display_advanced_options is True:
            self.maxcost_var = self.label_entry(
                def_maxcost, "Max. Cost:", "", advanced=True
            )
        elif self.maxcost_var is None:
            self.maxcost_var = tk.StringVar(self.master)
            self.maxcost_var.set(str(def_maxcost))
        self.quick_var = tk.IntVar(self.master)
        self.quick_var.set(0)
        quick_checkbox = tk.Checkbutton(
            self.frame_options, text="Quick & Approximate", variable=self.quick_var
        )
        quick_checkbox.grid(row=self.options_row, columnspan=2, sticky=tk.E)
        self.options_row += 1
        self.label_separator(simpleonly=True)
        self.label_title("Create Histogram Step:")
        self.default_histogram_choice = 7
        self.hist_choices = [
            "Number vs Diameter",
            "Number vs Surface",
            "Number vs Volume",
            "Mass vs Diameter",
            "Mass vs Surface",
            "Mass vs Volume",
            "Available mass vs Diameter",
            "Available mass vs Surface",
            "Available mass vs Volume",
            "Surface vs Diameter",
            "Surface vs Surface",
            "Surface vs Volume",
        ]
        self.hist_codes = [
            "num_diam",
            "num_surf",
            "num_vol",
            "mass_diam",
            "mass_surf",
            "mass_vol",
            "av_mass_diam",
            "av_mass_surf",
            "av_mass_vol",
            "surf_diam",
            "surf_surf",
            "surf_vol",
        ]
        self.histogram_type = self.dropdown_entry(
            "Histogram Options:",
            self.hist_choices,
            self.change_histogram_type,
            default_choice_index=self.default_histogram_choice,
        )
        self.legend_choices = [
            "Best",
            "Upper Right",
            "Upper Left",
            "Lower Right",
            "Lower Left",
            "Center Right",
            "Center Left",
            "Lower Center",
            "Upper Center",
            "Right",
            "Center",
        ]
        self.legend_type = self.dropdown_entry(
            "Label Position:", self.legend_choices, self.change_histogram_type
        )
        self.data_label_var = self.label_entry(
            "Current Data",
            "Data Label:",
            "",
            columnspan=2,
            width=self.width_entries * 3,
            event_on_enter="create_histogram",
        )
        (
            self.comparison_data_label_var,
            self.comparison_data_label_id,
            self.simple_comparison_data_label_id,
        ) = self.label_entry(
            "Comparison Data",
            "Comparison Label:",
            "",
            entry_id=True,
            columnspan=2,
            width=self.width_entries * 3,
            event_on_enter="create_histogram",
        )
        self.comparison_data_label_id.config(state=tk.DISABLED)
        self.simple_comparison_data_label_id.config(state=tk.DISABLED)
        self.xaxis_auto_var = tk.IntVar(self.master)
        self.xaxis_auto_var.set(1)
        xaxis_auto_checkbox = tk.Checkbutton(
            self.frame_options,
            text="Automated X axis | ",
            variable=self.xaxis_auto_var,
            command=self.xaxis_auto_event,
        )
        xaxis_auto_checkbox.grid(
            row=self.options_row, columnspan=1, sticky=tk.E, column=0
        )
        self.xmin_var, self.xmin_var_id = self.label_entry(
            def_min_x_axis,
            "Min. X Axis:",
            "",
            entry_id=True,
            addcol=1,
            event_on_enter="create_histogram",
            advanced=True,
            clear_on_click=True,
        )
        self.xlog_var = tk.IntVar(self.master)
        self.xlog_var.set(1)
        xlog_checkbox = tk.Checkbutton(
            self.frame_options,
            text="Log X axis | ",
            variable=self.xlog_var,
            command=self.xlog_event,
        )
        xlog_checkbox.grid(row=self.options_row, columnspan=1, sticky=tk.E, column=0)
        self.xmax_var, self.xmax_var_id = self.label_entry(
            def_max_x_axis,
            "Max. X Axis:",
            "",
            entry_id=True,
            addcol=1,
            event_on_enter="create_histogram",
            advanced=True,
            clear_on_click=True,
        )
        self.xmin_var_id.config(state=tk.DISABLED)
        self.xmax_var_id.config(state=tk.DISABLED)
        self.options_row += 1
        self.nbins_auto_var = tk.IntVar(self.master)
        self.nbins_auto_var.set(1)
        nbins_auto_checkbox = tk.Checkbutton(
            self.frame_options,
            text="Automated bins | ",
            variable=self.nbins_auto_var,
            command=self.nbins_auto_event,
        )
        nbins_auto_checkbox.grid(
            row=self.options_row, columnspan=1, column=0, sticky=tk.E
        )
        self.nbins_var, self.nbins_var_id = self.label_entry(
            10,
            "Num. bins:",
            "",
            entry_id=True,
            addcol=1,
            event_on_enter="create_histogram",
            advanced=True,
            clear_on_click=True,
        )
        self.nbins_var_id.config(state=tk.DISABLED)
        self.label_title("Output Options:", advanced=True)
        output_dir_button = tk.Button(
            self.frame_options,
            text="Select Output Directory:",
            command=self.select_output_dir,
        )
        output_dir_button.grid(row=self.options_row, sticky=tk.E)
        self.output_dir_var, self.output_dir_label_id = self.label_entry(
            self.output_dir,
            "",
            "",
            entry_id=True,
            columnspan=2,
            width=self.width_entries * 3,
            advanced=True,
        )
        self.output_dir_label_id.config(state=tk.DISABLED)
        self.options_row += 1
        self.session_name_var = self.label_entry(
            def_session_name,
            "Base of File Names:",
            "",
            columnspan=2,
            width=self.width_entries * 3,
            advanced=True,
        )
        self.label_separator(simpleonly=True)
        self.label_title("Display Options:")
        choices = [
            original_image_display_name,
            threshold_image_display_name,
            outlines_image_display_name,
            histogram_image_display_name,
        ]
        self.display_type = self.dropdown_entry(
            "Display Type:", choices, self.change_display_type
        )
        self.previous_display_type = choices[0]
        self.label_separator(simpleonly=True)
        self.label_separator(simpleonly=True)
        self.reset_zoom_button = tk.Button(
            self.frame_options, text="Reset View", command=self.reset_zoom
        )
        self.reset_zoom_button.grid(
            row=self.options_row, column=2, columnspan=1, sticky=tk.W
        )
        self.options_row += 1
        self.simple_zoom_in_button = tk.Button(
            self.simple_frame_options, text="Zoom In", command=self.zoom_in_button
        )
        self.simple_zoom_in_button.grid(
            row=self.simple_options_row, column=0, columnspan=1, sticky=tk.E
        )
        self.simple_zoom_out_button = tk.Button(
            self.simple_frame_options, text="Zoom Out", command=self.zoom_out_button
        )
        self.simple_zoom_out_button.grid(
            row=self.simple_options_row, column=1, columnspan=1, sticky=tk.W
        )
        self.simple_reset_zoom_button = tk.Button(
            self.simple_frame_options, text="Reset View", command=self.reset_zoom
        )
        self.simple_reset_zoom_button.grid(
            row=self.simple_options_row, column=2, columnspan=1, sticky=tk.W
        )
        self.simple_options_row += 1
        reset_params_button = tk.Button(
            self.frame_options, text="Reset All Parameters", command=self.reset_status
        )
        reset_params_button.grid(
            row=self.options_row, column=1, columnspan=2, sticky=tk.E
        )
        simple_reset_params_button = tk.Button(
            self.simple_frame_options,
            text="Reset All Parameters",
            command=self.reset_status,
        )
        simple_reset_params_button.grid(
            row=self.simple_options_row, column=1, columnspan=2, sticky=tk.E
        )
        if self.expert_mode is True:
            self.frame_options.tkraise()
        frame_stats_bg = "gray60"
        self.frame_stats = tk.Frame(
            self.container_options, bg=frame_stats_bg, padx=2, pady=10
        )
        self.frame_stats.grid(row=0, column=1, sticky="new", rowspan=1)
        title_label = tk.Label(
            self.frame_stats,
            text="Properties of the Particle Distribution:",
            font="Helvetica 16 bold",
            bg=frame_stats_bg,
        )
        title_label.grid(row=0, sticky=tk.W, padx=self.title_padx, columnspan=12)
        stats_colsep_width = 3
        stats_row = 1
        stats_column = 0
        stats_entry_width = 5
        self.diam_average_var = tk.StringVar(self.master)
        self.diam_average_var.set("None")
        diam_average_label = tk.Label(
            self.frame_stats,
            text="Average Diameter:",
            bg=frame_stats_bg,
            font="Helvetica 14 bold",
        )
        diam_average_label.grid(row=stats_row, sticky=tk.E, column=stats_column)
        diam_average_entry = tk.Label(
            self.frame_stats,
            textvariable=self.diam_average_var,
            width=stats_entry_width,
            bg=frame_stats_bg,
        )
        diam_average_entry.grid(row=stats_row, column=stats_column + 1)
        unit_label = tk.Label(self.frame_stats, text="(mm)", bg=frame_stats_bg)
        unit_label.grid(row=stats_row, column=stats_column + 2, sticky=tk.W)
        stats_row += 1
        self.diam_stddev_var = tk.StringVar(self.master)
        self.diam_stddev_var.set("None")
        diam_stddev_label = tk.Label(
            self.frame_stats,
            text="Scatter in Diameter:",
            bg=frame_stats_bg,
            font="Helvetica 14 bold",
        )
        diam_stddev_label.grid(row=stats_row, sticky=tk.E, column=stats_column)
        diam_stddev_entry = tk.Label(
            self.frame_stats,
            textvariable=self.diam_stddev_var,
            width=stats_entry_width,
            bg=frame_stats_bg,
        )
        diam_stddev_entry.grid(row=stats_row, column=stats_column + 1)
        unit_label = tk.Label(self.frame_stats, text="(mm)", bg=frame_stats_bg)
        unit_label.grid(row=stats_row, column=stats_column + 2, sticky=tk.W)
        stats_column += 3
        stats_row = 1
        separator_label = tk.Label(
            self.frame_stats, text="", width=stats_colsep_width, bg=frame_stats_bg
        )
        separator_label.grid(row=stats_row, column=stats_column)
        stats_column += 1
        self.surf_average_var = tk.StringVar(self.master)
        self.surf_average_var.set("None")
        surf_average_label = tk.Label(
            self.frame_stats,
            text="Average Surface:",
            bg=frame_stats_bg,
            font="Helvetica 14 bold",
        )
        surf_average_label.grid(row=stats_row, sticky=tk.E, column=stats_column)
        surf_average_entry = tk.Label(
            self.frame_stats,
            textvariable=self.surf_average_var,
            width=stats_entry_width,
            bg=frame_stats_bg,
        )
        surf_average_entry.grid(row=stats_row, column=stats_column + 1)
        unit_label = tk.Label(self.frame_stats, text="(mm²)", bg=frame_stats_bg)
        unit_label.grid(row=stats_row, column=stats_column + 2, sticky=tk.W)
        stats_row += 1
        self.surf_stddev_var = tk.StringVar(self.master)
        self.surf_stddev_var.set("None")
        surf_stddev_label = tk.Label(
            self.frame_stats,
            text="Scatter in Surface:",
            bg=frame_stats_bg,
            font="Helvetica 14 bold",
        )
        surf_stddev_label.grid(row=stats_row, sticky=tk.E, column=stats_column)
        surf_stddev_entry = tk.Label(
            self.frame_stats,
            textvariable=self.surf_stddev_var,
            width=stats_entry_width,
            bg=frame_stats_bg,
        )
        surf_stddev_entry.grid(row=stats_row, column=stats_column + 1)
        unit_label = tk.Label(self.frame_stats, text="(mm²)", bg=frame_stats_bg)
        unit_label.grid(row=stats_row, column=stats_column + 2, sticky=tk.W)
        stats_column += 3
        stats_row = 1
        separator_label = tk.Label(
            self.frame_stats, text="", width=stats_colsep_width, bg=frame_stats_bg
        )
        separator_label.grid(row=stats_row, column=stats_column)
        stats_column += 1
        self.eff_var = tk.StringVar(self.master)
        self.eff_var.set("None")
        eff_label = tk.Label(
            self.frame_stats,
            text="Efficiency:",
            bg=frame_stats_bg,
            font="Helvetica 14 bold",
        )
        eff_label.grid(row=stats_row, sticky=tk.E, column=stats_column)
        eff_entry = tk.Label(
            self.frame_stats,
            textvariable=self.eff_var,
            width=stats_entry_width,
            bg=frame_stats_bg,
        )
        eff_entry.grid(row=stats_row, column=stats_column + 1)
        unit_label = tk.Label(self.frame_stats, text="(%)", bg=frame_stats_bg)
        unit_label.grid(row=stats_row, column=stats_column + 2, sticky=tk.W)
        stats_row += 1
        self.q_var = tk.StringVar(self.master)
        self.q_var.set("None")
        eff_label = tk.Label(
            self.frame_stats,
            text="Quality:",
            bg=frame_stats_bg,
            font="Helvetica 14 bold",
        )
        eff_label.grid(row=stats_row, sticky=tk.E, column=stats_column)
        eff_entry = tk.Label(
            self.frame_stats,
            textvariable=self.q_var,
            width=stats_entry_width,
            bg=frame_stats_bg,
        )
        eff_entry.grid(row=stats_row, column=stats_column + 1)
        unit_label = tk.Label(self.frame_stats, text="", bg=frame_stats_bg)
        unit_label.grid(row=stats_row, column=stats_column + 2, sticky=tk.W)
        image_canvas_bg = "gray40"
        self.image_canvas = tk.Canvas(
            self.container_options,
            width=self.canvas_width,
            height=self.canvas_height,
            bg=image_canvas_bg,
        )
        self.image_canvas.grid(row=1, column=1, sticky=tk.N, rowspan=24)
        self.image_canvas.pack_propagate(0)
        self.image_canvas.focus_set()
        self.noimage_label = tk.Label(
            self.image_canvas,
            text="No Image Loaded",
            anchor=tk.CENTER,
            bg=image_canvas_bg,
            font="Helvetica 22 bold",
            width=self.canvas_width,
            height=self.canvas_height,
        )
        self.noimage_label.pack(side=tk.LEFT)
        open_image_button = tk.Button(
            toolbar,
            text="Open Image",
            command=lambda: self.open_image(None),
            highlightbackground=toolbar_bg,
        )
        open_image_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        ref_obj_button = tk.Button(
            toolbar,
            text="Select Reference Object",
            command=lambda: self.select_reference_object_mouse(None),
            highlightbackground=toolbar_bg,
        )
        ref_obj_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        region_button = tk.Button(
            toolbar,
            text="Select Analysis Region",
            command=lambda: self.select_region(None),
            highlightbackground=toolbar_bg,
        )
        region_button.pack(side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady)
        threshold_image_button = tk.Button(
            toolbar,
            text="Threshold Image",
            command=lambda: self.threshold_image(None),
            highlightbackground=toolbar_bg,
        )
        threshold_image_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        psd_button = tk.Button(
            toolbar,
            text="Launch Particle Detection",
            command=lambda: self.launch_psd(None),
            highlightbackground=toolbar_bg,
        )
        psd_button.pack(side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady)
        erase_button = tk.Button(
            toolbar,
            text="Erase Clusters",
            command=lambda: self.erase_clusters(None),
            highlightbackground=toolbar_bg,
        )
        erase_button.pack(side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady)
        histogram_button = tk.Button(
            toolbar,
            text="Create Histogram",
            command=lambda: self.create_histogram(None),
            highlightbackground=toolbar_bg,
        )
        histogram_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        blog_button = tk.Button(
            toolbar,
            text="Read Coffee Ad Astra Blog",
            command=self.blog_goto,
            highlightbackground=toolbar_bg,
        )
        blog_button.pack(side=tk.RIGHT, padx=self.toolbar_padx, pady=self.toolbar_pady)
        downsample_button = tk.Button(
            toolbar2,
            text="Reduce Image Quality",
            command=self.downsample_image,
            highlightbackground=toolbar_bg,
        )
        downsample_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        load_data_button = tk.Button(
            toolbar2,
            text="Load Data",
            command=lambda: self.load_data(None),
            highlightbackground=toolbar_bg,
        )
        load_data_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        load_comparison_data_button = tk.Button(
            toolbar2,
            text="Load Comparison Data",
            command=lambda: self.load_comparison_data(None),
            highlightbackground=toolbar_bg,
        )
        load_comparison_data_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        flush_comparison_data_button = tk.Button(
            toolbar2,
            text="Flush Comparison Data",
            command=self.flush_comparison_data,
            highlightbackground=toolbar_bg,
        )
        flush_comparison_data_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        save_button = tk.Button(
            toolbar2,
            text="Save Data",
            command=lambda: self.save_data(None),
            highlightbackground=toolbar_bg,
        )
        save_button.pack(side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady)
        savehist_button = tk.Button(
            toolbar2,
            text="Save View",
            command=lambda: self.save_histogram(None),
            highlightbackground=toolbar_bg,
        )
        savehist_button.pack(
            side=tk.LEFT, padx=self.toolbar_padx, pady=self.toolbar_pady
        )
        quit_button = tk.Button(
            toolbar2, text="Quit", command=self.quit_gui, highlightbackground=toolbar_bg
        )
        quit_button.pack(side=tk.RIGHT, padx=self.toolbar_padx, pady=self.toolbar_pady)
        reset_button = tk.Button(
            toolbar2,
            text="Reboot",
            command=self.reset_gui,
            highlightbackground=toolbar_bg,
        )
        reset_button.pack(side=tk.RIGHT, padx=self.toolbar_padx, pady=self.toolbar_pady)
        help_button = tk.Button(
            toolbar2,
            text="Help",
            command=self.launch_help,
            highlightbackground=toolbar_bg,
        )
        help_button.pack(side=tk.RIGHT, padx=self.toolbar_padx, pady=self.toolbar_pady)
        menu = tk.Menu(root)
        self.master.config(menu=menu)
        subMenu = tk.Menu(menu)
        menu.add_cascade(label="File", menu=subMenu)
        subMenu.add_command(
            label="Open Image...", command=lambda: self.open_image(None)
        )
        subMenu.add_separator()
        subMenu.add_command(
            label="Reduce Image Quality...", command=self.downsample_image
        )
        subMenu.add_separator()
        subMenu.add_command(
            label="Turn Expert Mode On/Off...", command=self.toggle_expert_mode
        )
        subMenu.add_separator()

        subMenu.add_separator()
        subMenu.add_command(label="Quit", command=self.quit_gui)
        self.image_canvas.bind("<Motion>", self.motion)
        self.image_canvas.bind("<ButtonPress-1>", self.move_start)
        self.image_canvas.bind("<ButtonRelease-1>", self.release_mouse)
        self.image_canvas.bind("<B1-Motion>", self.move_move)
        self.image_canvas.bind_all("<Command-i>", self.zoom_in)
        self.image_canvas.bind_all("<Command-o>", self.zoom_out)
        self.master.bind_all("<Command-m>", self.open_image)
        self.master.bind_all("<Command-r>", self.select_reference_object_mouse)
        self.master.bind_all("<Command-a>", self.select_region)
        self.master.bind_all("<Command-t>", self.threshold_image)
        self.master.bind_all("<Command-p>", self.launch_psd)
        self.master.bind_all("<Command-h>", self.create_histogram)
        self.master.bind_all("<Command-s>", self.save_data)
        self.master.bind_all("<Command-l>", self.load_data)
        self.master.bind_all("<Control-c>", self.load_comparison_data)
        self.master.bind_all("<Control-v>", self.save_histogram)
        self.master.bind_all("<Command-e>", lambda event: self.toggle_expert_mode())
        self.image_canvas.bind_all("<Escape>", self.quit_region_select)
        self.image_canvas.bind_all("<Return>", self.quit_region_select)

    def xlog_event(self):
        if self.img_histogram is not None:
            self.create_histogram(None)

    def nbins_auto_event(self):
        if self.nbins_auto_var.get() == 0:
            self.nbins_var_id.config(state=tk.NORMAL)
        if self.nbins_auto_var.get() == 1:
            self.nbins_var_id.config(state=tk.DISABLED)
        if self.img_histogram is not None:
            self.create_histogram(None)

    def xaxis_auto_event(self):
        if self.img_histogram is not None:
            self.create_histogram(None)
        if self.xaxis_auto_var.get() == 0:
            self.xmin_var_id.config(state=tk.NORMAL)
            self.xmax_var_id.config(state=tk.NORMAL)
        if self.xaxis_auto_var.get() == 1:
            self.xmin_var_id.config(state=tk.DISABLED)
            self.xmax_var_id.config(state=tk.DISABLED)

    @guard_action
    def select_reference_object_mouse(self, event):
        if self.img_source is None:
            self.status_var.set(
                "Original Image not Loaded Yet... Use Open Image Button..."
            )
            self.master.update()
            return
        self.mouse_click_mode = "SELECT_REFERENCE_OBJECT_READY"
        self.status_var.set(
            "Use your mouse to click on one side of the reference object... You will then need to click again to set up a measuring line..."
        )
        self.master.update()

    @guard_action
    def select_region(self, event):
        if self.mouse_click_mode == "SELECT_REGION":
            self.quit_region_select(None)
            return
        if self.img_source is None:
            self.status_var.set(
                "Original Image not Loaded Yet... Use Open Image Button..."
            )
            self.master.update()
            return
        self.image_canvas.delete(self.image_canvas.find_withtag("line"))
        self.polygon_alpha = None
        self.polygon_beta = None
        self.redraw(x=self.last_image_x, y=self.last_image_y)
        self.status_var.set(
            "Click on the image to draw a polygon enclosing the coffee grounds, then press q..."
        )
        self.master.update()
        self.mouse_click_mode = "SELECT_REGION"

    @guard_action
    def quit_region_select(self, event):
        if self.erase_clusters_mode is True:
            self.status_var.set("The 'Erase Clusters' mode was deactivated.")
            self.master.update()
            self.erase_clusters_mode = False
            return
        if self.mouse_click_mode == "SELECT_REGION":
            self.mouse_click_mode = None
            if self.selreg_current_line is not None:
                self.image_canvas.delete(self.selreg_current_line)
                self.selreg_current_line = None
            if self.polygon_alpha is None:
                polysize = 0
            else:
                polysize = self.polygon_alpha.size
            if polysize < 3:
                self.image_canvas.delete(self.image_canvas.find_withtag("line"))
                self.polygon_alpha = None
                self.polygon_beta = None
                self.status_var.set(
                    "Analysis Region Did Not Have Enough Corners (at least 3 are needed)..."
                )
            else:
                self.polygon_alpha = np.append(
                    self.polygon_alpha, self.polygon_alpha[0]
                )
                self.polygon_beta = np.append(self.polygon_beta, self.polygon_beta[0])
                self.status_var.set("Analysis Region Was Set...")
            self.redraw(x=self.last_image_x, y=self.last_image_y)
            self.master.update()

    def blog_goto(self, *args):
        webbrowser.open("https://coffeeadastra.com")

    def change_reference_object(self, *args):
        self.physical_length_var.set(
            reference_objects_dict[self.reference_object.get()]
        )
        if self.reference_object.get() == "Custom":
            self.physical_length_id.config(state=tk.NORMAL)
            self.simple_physical_length_id.config(state=tk.NORMAL)
        else:
            self.physical_length_id.config(state=tk.DISABLED)
            self.simple_physical_length_id.config(state=tk.DISABLED)
        self.update_pixel_scale()
        self.status_var.set(
            "Reference Object set to " + self.reference_object.get() + "..."
        )
        self.master.update()

    def update_pixel_scale(self) -> None:
        try:
            physical = validate_scale(float(self.physical_length_var.get()))
            scale = validate_scale(float(self.pixel_length_var.get()) / physical)
        except ValueError, TypeError:
            self.pixel_scale_var.set("None")
        else:
            self.pixel_scale_var.set(f"{scale:.3f}")
        self.update_statistics()

    def change_histogram_type(self, *args):
        if self.histogram_type.get() == "Extraction Yield Distribution":
            self.xlog_var.set(0)
        if self.img_histogram is not None:
            self.create_histogram(None)

    def change_display_type(self, *args):
        if self.display_type.get() == original_image_display_name:
            if self.img_source is None:
                self.status_var.set(
                    "Original Image not Loaded Yet... Use Open Image Button..."
                )
                self.display_type.set(self.previous_display_type)
                self.master.update()
                return
        if self.display_type.get() == threshold_image_display_name:
            if self.img_threshold is None:
                self.status_var.set(
                    "Thresholded Image not Available Yet... Use Threshold Image Button..."
                )
                self.display_type.set(self.previous_display_type)
                self.master.update()
                return
        if self.display_type.get() == outlines_image_display_name:
            if self.img_clusters is None:
                self.status_var.set(
                    "Cluster Outlines Image not Available Yet... Use Launch Particle Detection Button..."
                )
                self.display_type.set(self.previous_display_type)
                self.master.update()
                return
        if self.display_type.get() == histogram_image_display_name:
            if self.img_histogram is None:
                self.status_var.set(
                    "Histogram Figure not Available Yet... Use Create Histogram Figure Button..."
                )
                self.display_type.set(self.previous_display_type)
                self.master.update()
                return
        if self.display_type.get() != outlines_image_display_name:
            self.erase_clusters_mode = False
        if self.display_type.get() == histogram_image_display_name:
            self.image_canvas.delete(self.image_canvas.find_withtag("line"))
            self.polygon_alpha = None
            self.polygon_beta = None
            self.image_canvas.xview_moveto(0)
            self.image_canvas.yview_moveto(0)
            self.last_image_x = self.canvas_width / 2
            self.last_image_y = self.canvas_height / 2
            self.scale = 1
            self.simple_zoom_in_button.config(state=tk.DISABLED)
            self.simple_zoom_out_button.config(state=tk.DISABLED)
            self.reset_zoom_button.config(state=tk.DISABLED)
        elif self.previous_display_type == histogram_image_display_name:
            self.scale = self.original_scale
            self.simple_zoom_in_button.config(state=tk.NORMAL)
            self.simple_zoom_out_button.config(state=tk.NORMAL)
            self.reset_zoom_button.config(state=tk.NORMAL)
        self.redraw(x=self.last_image_x, y=self.last_image_y)
        self.status_var.set("Changed Display to " + self.display_type.get() + "...")
        self.previous_display_type = self.display_type.get()
        self.master.update()

    def dropdown_entry(
        self, label, choices, method, default_choice_index=0, advanced=False
    ):
        data_var = tk.StringVar(self.master)
        data_var.set(choices[default_choice_index])
        dropdown_label = tk.Label(self.frame_options, text=label)
        dropdown_label.grid(row=self.options_row, sticky=tk.E)
        if advanced is False:
            simple_dropdown_label = tk.Label(self.simple_frame_options, text=label)
            simple_dropdown_label.grid(row=self.simple_options_row, sticky=tk.E)
        dropdown_menu = tk.OptionMenu(self.frame_options, data_var, *choices)
        dropdown_menu.grid(row=self.options_row, column=1, columnspan=2, sticky=tk.EW)
        if advanced is False:
            simple_dropdown_menu = tk.OptionMenu(
                self.simple_frame_options, data_var, *choices
            )
            simple_dropdown_menu.grid(
                row=self.simple_options_row, column=1, columnspan=2, sticky=tk.EW
            )
        data_var.trace_add("write", method)
        self.options_row += 1
        if advanced is False:
            self.simple_options_row += 1
        return data_var

    def label_entry(
        self,
        default_var,
        text,
        units_text,
        columnspan=None,
        width=None,
        entry_id=False,
        clear_on_click=False,
        event_on_entry=None,
        addcol=0,
        event_on_enter=None,
        advanced=False,
    ):
        if width is None:
            width = self.width_entries
        data_var = tk.StringVar(self.master)
        data_var.set(str(default_var))
        if text != "":
            data_label = tk.Label(self.frame_options, text=text)
            data_label.grid(row=self.options_row, sticky=tk.E, column=addcol)
            if advanced is False:
                simple_data_label = tk.Label(self.simple_frame_options, text=text)
                simple_data_label.grid(
                    row=self.simple_options_row, sticky=tk.E, column=addcol
                )
        if event_on_entry is not None:
            function_trigger = getattr(self, event_on_entry)
            data_var.trace_add(
                "write", lambda name, index, mode, data_var=data_var: function_trigger()
            )
        data_entry = tk.Entry(self.frame_options, textvariable=data_var, width=width)
        data_entry.grid(row=self.options_row, column=1 + addcol, columnspan=columnspan)
        if clear_on_click is True:
            data_entry.bind("<Button-1>", lambda event: self.clear_entry(data_entry))
        if advanced is False:
            simple_data_entry = tk.Entry(
                self.simple_frame_options, textvariable=data_var, width=width
            )
            simple_data_entry.grid(
                row=self.simple_options_row, column=1 + addcol, columnspan=columnspan
            )
            if clear_on_click is True:
                simple_data_entry.bind(
                    "<Button-1>", lambda event: self.clear_entry(simple_data_entry)
                )
        if event_on_enter is not None:
            function_trigger = getattr(self, event_on_enter)
            data_entry.bind("<Return>", function_trigger)
            if advanced is False:
                simple_data_entry.bind("<Return>", function_trigger)
        if units_text != "":
            data_label_units = tk.Label(self.frame_options, text=units_text)
            data_label_units.grid(row=self.options_row, column=2 + addcol, sticky=tk.W)
            if advanced is False:
                simple_data_label_units = tk.Label(
                    self.simple_frame_options, text=units_text
                )
                simple_data_label_units.grid(
                    row=self.simple_options_row, column=2 + addcol, sticky=tk.W
                )
        self.options_row += 1
        if advanced is False:
            self.simple_options_row += 1
        if entry_id is True:
            if advanced is False:
                return (data_var, data_entry, simple_data_entry)
            else:
                return (data_var, data_entry)
        else:
            return data_var

    def clear_entry(self, entry_id):
        entry_id.delete(0, "end")

    def label_title(self, text, advanced=False):
        if advanced is False:
            title_label = tk.Label(
                self.simple_frame_options, text=text, font="Helvetica 16 bold"
            )
            title_label.grid(
                row=self.simple_options_row,
                sticky=tk.W,
                padx=self.title_padx,
                columnspan=2,
            )
            self.simple_options_row += 1
        title_label = tk.Label(self.frame_options, text=text, font="Helvetica 16 bold")
        title_label.grid(
            row=self.options_row, sticky=tk.W, padx=self.title_padx, columnspan=2
        )
        self.options_row += 1

    def label_separator(self, advanced=False, simpleonly=False):
        if simpleonly is False:
            separator_label = tk.Label(self.frame_options, text="")
            separator_label.grid(row=self.options_row)
            self.options_row += 1
        if advanced is False:
            simple_separator_label = tk.Label(self.simple_frame_options, text="")
            simple_separator_label.grid(row=self.simple_options_row)
            self.simple_options_row += 1

    def redraw(self, x=0, y=0):
        self.image_canvas.delete("all")
        if self.image_id:
            self.image_canvas.delete(self.image_id)
        if self.display_type.get() == original_image_display_name:
            self.img = self.img_source
        if self.display_type.get() == threshold_image_display_name:
            self.img = self.img_threshold
        if self.display_type.get() == outlines_image_display_name:
            self.img = self.img_clusters
        if self.display_type.get() == histogram_image_display_name:
            self.img = self.img_histogram
            self.polygon_alpha = None
            self.polygon_beta = None
        iw, ih = self.img.size
        size = (max(1, int(iw * self.scale)), max(1, int(ih * self.scale)))
        self.image_obj = ImageTk.PhotoImage(self.img.resize(size), master=self.master)
        self.image_id = self.image_canvas.create_image(x, y, image=self.image_obj)
        if self.polygon_alpha is not None:
            npoly = self.polygon_alpha.size
            if npoly > 1:
                image_x, image_y = self.image_canvas.coords(self.image_id)
                image_x -= self.image_canvas.canvasx(0)
                image_y -= self.image_canvas.canvasy(0)
                orig_nx, orig_ny = self.img.size
                for i in range(npoly - 1):
                    line_x_start = (
                        self.polygon_alpha[i] - orig_nx / 2
                    ) * self.scale + image_x
                    line_y_start = (
                        self.polygon_beta[i] - orig_ny / 2
                    ) * self.scale + image_y
                    line_x_end = (
                        self.polygon_alpha[i + 1] - orig_nx / 2
                    ) * self.scale + image_x
                    line_y_end = (
                        self.polygon_beta[i + 1] - orig_ny / 2
                    ) * self.scale + image_y
                    line_x_start += self.image_canvas.canvasx(0)
                    line_y_start += self.image_canvas.canvasy(0)
                    line_x_end += self.image_canvas.canvasx(0)
                    line_y_end += self.image_canvas.canvasy(0)
                    self.image_canvas.create_line(
                        line_x_start, line_y_start, line_x_end, line_y_end, fill="green"
                    )

    @guard_action
    def release_mouse(self, event):
        if self.mouse_click_mode == "SELECT_REFERENCE_OBJECT":
            self.mouse_click_mode = None
            self.image_canvas.scan_mark(event.x, event.y)
            self.status_var.set(
                "The length of the the reference object was set to "
                + self.pixel_length_var.get()
                + " pixels... Now select its physical size with the library in the Reference Object dropdown menu, or with a custom Reference Physical Size..."
            )
            self.master.update()
        if self.mouse_click_mode == "SELECT_REFERENCE_OBJECT_READY":
            if self.display_type.get() == histogram_image_display_name:
                return
            self.line_start(event)
            self.mouse_click_mode = "SELECT_REFERENCE_OBJECT"
            self.status_var.set(
                "Drag the red line across the reference object then click again... Be careful to exclude shadows, and make sure that the Angle of Reference Line entry is satisfactory to you..."
            )
            self.master.update()

    @guard_action
    def move_start(self, event):
        self.image_canvas.focus_set()
        if self.display_type.get() == histogram_image_display_name:
            return
        if self.erase_clusters_mode is True:
            image_x, image_y = self.image_canvas.coords(self.image_id)
            image_x -= self.image_canvas.canvasx(0)
            image_y -= self.image_canvas.canvasy(0)
            orig_nx, orig_ny = self.img.size
            mouse_alpha = orig_nx / 2 + (self.mouse_x - image_x) / self.scale
            mouse_beta = orig_ny / 2 + (self.mouse_y - image_y) / self.scale
            rad = float(self.erase_circle_radius) / float(self.scale)
            dist = np.sqrt(
                (self.clusters_xmean - mouse_beta) ** 2
                + (self.clusters_ymean - mouse_alpha) ** 2
            )
            delclus = np.where(dist <= rad)[0]
            if (len(delclus) != 0) & (len(delclus) >= self.nclusters):
                self.status_var.set("All clusters cannot be erased.")
                self.master.update()
                return
            if (len(delclus) != 0) & (len(delclus) < self.nclusters):
                self.cluster_data = np.delete(self.cluster_data, delclus)
                self.refresh_cluster_data()
                self.status_var.set(str(len(delclus)) + " clusters were erased.")
                self.master.update()
                if self.erase_clusters_mode is True:
                    self.eraser_circle_refresh(
                        SimpleNamespace(x=self.mouse_x, y=self.mouse_y)
                    )
        if self.mouse_click_mode is None:
            self.image_canvas.scan_mark(event.x, event.y)
        if self.mouse_click_mode == "SELECT_REGION":
            image_x, image_y = self.image_canvas.coords(self.image_id)
            image_x -= self.image_canvas.canvasx(0)
            image_y -= self.image_canvas.canvasy(0)
            orig_nx, orig_ny = self.img.size
            mouse_alpha = orig_nx / 2 + (self.mouse_x - image_x) / self.scale
            mouse_beta = orig_ny / 2 + (self.mouse_y - image_y) / self.scale
            if self.polygon_alpha is None:
                self.polygon_alpha = np.array([mouse_alpha])
                self.polygon_beta = np.array([mouse_beta])
            else:
                self.polygon_alpha = np.append(self.polygon_alpha, mouse_alpha)
                self.polygon_beta = np.append(self.polygon_beta, mouse_beta)
            self.redraw(x=self.last_image_x, y=self.last_image_y)

    def move_move(self, event):
        if self.display_type.get() == histogram_image_display_name:
            return
        if self.mouse_click_mode is None:
            self.image_canvas.scan_dragto(event.x, event.y, gain=1)

    def line_start(self, event):
        if self.display_type.get() == histogram_image_display_name:
            return
        self.linex_start = event.x + self.image_canvas.canvasx(0)
        self.liney_start = event.y + self.image_canvas.canvasy(0)

    def line_move(self, event):
        if self.display_type.get() == histogram_image_display_name:
            return
        if self.line_obj is not None:
            self.image_canvas.delete(self.line_obj)
        cur_x = event.x + self.image_canvas.canvasx(0)
        cur_y = event.y + self.image_canvas.canvasy(0)
        self.line_obj = self.image_canvas.create_line(
            self.linex_start, self.liney_start, cur_x, cur_y, fill="red"
        )
        line_length = (
            np.sqrt((cur_x - self.linex_start) ** 2 + (cur_y - self.liney_start) ** 2)
            / self.scale
        )
        line_length_str = "{0:.{1}f}".format(line_length, 1)
        self.pixel_length_var.set(line_length_str)
        line_angle = (
            180.0
            / np.pi
            * np.arctan2(cur_y - self.liney_start, cur_x - self.linex_start)
        )
        line_angle_str = "{0:.{1}f}".format(line_angle, 1)
        self.physical_angle_var.set(line_angle_str)
        self.update_pixel_scale()

    def eraser_circle_refresh(self, event):
        cen_x = event.x
        cen_y = event.y
        cen_x += self.image_canvas.canvasx(0)
        cen_y += self.image_canvas.canvasy(0)
        rad = float(self.erase_circle_radius)
        x0 = cen_x - rad
        y0 = cen_y - rad
        x1 = cen_x + rad
        y1 = cen_y + rad
        if self.erasemode_current_circle is not None:
            self.image_canvas.delete(self.erasemode_current_circle)
        self.erasemode_current_circle = self.image_canvas.create_oval(
            x0, y0, x1, y1, outline="orange", width=2
        )

    def motion(self, event, only_refresh_display=False):
        if self.cursor_text is not None:
            self.image_canvas.delete(self.cursor_text)
        if self.display_type.get() == histogram_image_display_name:
            return
        self.mouse_x, self.mouse_y = (event.x, event.y)
        if self.erase_clusters_mode is True:
            self.eraser_circle_refresh(event)
        if self.mouse_click_mode == "SELECT_REFERENCE_OBJECT":
            self.line_move(event)
        if self.mouse_click_mode == "SELECT_REGION":
            if self.polygon_alpha is not None:
                image_x, image_y = self.image_canvas.coords(self.image_id)
                image_x -= self.image_canvas.canvasx(0)
                image_y -= self.image_canvas.canvasy(0)
                orig_nx, orig_ny = self.img.size
                line_x_start = (
                    self.polygon_alpha[-1] - orig_nx / 2
                ) * self.scale + image_x
                line_y_start = (
                    self.polygon_beta[-1] - orig_ny / 2
                ) * self.scale + image_y
                line_x_end = self.mouse_x
                line_y_end = self.mouse_y
                line_x_start += self.image_canvas.canvasx(0)
                line_y_start += self.image_canvas.canvasy(0)
                line_x_end += self.image_canvas.canvasx(0)
                line_y_end += self.image_canvas.canvasy(0)
                if self.selreg_current_line is not None:
                    self.image_canvas.delete(self.selreg_current_line)
                self.selreg_current_line = self.image_canvas.create_line(
                    line_x_start, line_y_start, line_x_end, line_y_end, fill="green"
                )

    def zoom_in_button(self):
        self.mouse_x, self.mouse_y = (self.last_image_x, self.last_image_y)
        self.zoom(None, 1)

    def zoom_out_button(self):
        self.mouse_x, self.mouse_y = (self.last_image_x, self.last_image_y)
        self.zoom(None, -1)

    def zoom_in(self, event):
        if self.master.focus_get() != self.image_canvas:
            return
        if self.display_type.get() == histogram_image_display_name:
            return
        self.zoom(event, 1)

    def zoom_out(self, event):
        if self.display_type.get() == histogram_image_display_name:
            return
        self.zoom(event, -1)

    @guard_action
    def zoom(self, event, directionality):
        if self.img is None or self.display_type.get() == histogram_image_display_name:
            return
        if event is None:
            event = SimpleNamespace(x=self.mouse_x, y=self.mouse_y)
        if directionality > 0:
            if self.scale / self.original_scale >= self.max_scale:
                return
        image_x, image_y = self.image_canvas.coords(self.image_id)
        image_x -= self.image_canvas.canvasx(0)
        image_y -= self.image_canvas.canvasy(0)
        orig_nx, orig_ny = self.img.size
        mouse_alpha = orig_nx / 2 + (self.mouse_x - image_x) / self.scale
        mouse_beta = orig_ny / 2 + (self.mouse_y - image_y) / self.scale
        if directionality > 0:
            self.scale *= 2
        if directionality < 0:
            self.scale /= 2
        new_image_x = self.mouse_x - (mouse_alpha - orig_nx / 2) * self.scale
        new_image_y = self.mouse_y - (mouse_beta - orig_ny / 2) * self.scale
        new_image_x += self.image_canvas.canvasx(0)
        new_image_y += self.image_canvas.canvasy(0)
        self.last_image_x = new_image_x
        self.last_image_y = new_image_y
        self.redraw(x=new_image_x, y=new_image_y)
        if self.erase_clusters_mode is True:
            event.x = self.mouse_x
            event.y = self.mouse_y
            self.eraser_circle_refresh(event)

    @guard_action
    def toggle_expert_mode(self):
        if self.expert_mode is False:
            self.frame_options.tkraise()
            self.expert_mode = True
            return
        if self.expert_mode is True:
            self.simple_frame_options.tkraise()
            self.expert_mode = False
            return

    @guard_action
    def reset_zoom(self):
        if self.img is None or self.display_type.get() == histogram_image_display_name:
            return
        self.status_var.set("Zoom Parameters Reset to Defaults...")
        self.scale = self.original_scale
        self.image_canvas.xview_moveto(0)
        self.image_canvas.yview_moveto(0)
        self.redraw(x=self.canvas_width / 2, y=self.canvas_height / 2)
        self.last_image_x = self.canvas_width / 2
        self.last_image_y = self.canvas_height / 2
        self.master.update()

    @guard_action
    def reset_status(self):
        self.threshold_var.set(str(def_threshold))
        self.max_cluster_axis_var.set(str(def_max_cluster_axis))
        self.min_surface_var.set(str(def_min_surface))
        self.min_roundness_var.set(str(def_min_roundness))
        self.quick_var.set(0)
        self.histogram_type.set(self.hist_choices[self.default_histogram_choice])
        self.xmin_var.set(str(def_min_x_axis))
        self.xmax_var.set(str(def_max_x_axis))
        self.xlog_var.set(1)
        self.output_dir = def_output_dir
        self.output_dir_var.set(self.output_dir)
        self.session_name_var.set(str(def_session_name))
        self.display_type.set(original_image_display_name)
        self.erase_clusters_mode = False
        if self.img_source is not None:
            self.reset_zoom()
        self.status_var.set("Parameters Reset to Defaults...")
        self.master.update()

    @guard_action
    def select_output_dir(self):
        self.master.update()
        directory = filedialog.askdirectory(
            initialdir=self.output_dir, title="Select an output directory"
        )
        if not directory:
            return
        self.output_dir = directory
        self.output_dir_var.set(self.output_dir)
        self.master.update()

    @guard_action
    def downsample_image(self) -> None:
        if self.img_source is None:
            self.status_var.set("Open an image before downsampling.")
            return
        width, height = self.img_source.size
        if width < 2 or height < 2:
            self.status_var.set("The image cannot be reduced further.")
            return
        image = self.img_source.resize(
            (width // 2, height // 2), Image.Resampling.LANCZOS
        )
        previous_scale = self.pixel_scale_var.get()
        self.reset_state()
        self.img_source = self.img = image
        self.display_type.set(original_image_display_name)
        self.previous_display_type = original_image_display_name
        self.scale = min(
            self.canvas_width / image.width, self.canvas_height / image.height
        )
        self.original_scale = self.scale
        if self.expert_mode:
            try:
                self.pixel_scale_var.set(str(validate_scale(float(previous_scale)) / 2))
            except ValueError, TypeError:
                self.pixel_scale_var.set("None")
        self.reset_zoom()
        self.status_var.set(
            f"Downsampled to {image.width} × {image.height}; check calibration before analysis"
        )

    def reset_state(self):
        self.polygon_alpha = None
        self.polygon_beta = None
        self._threshold = None
        self.mask_threshold = None
        self.mask_threshold_edge = None
        self.cluster_data = None
        self.mouse_click_mode = None
        self.img_threshold = None
        self.img_clusters = None
        self.img_histogram = None
        self.nclusters = None
        self.cluster_data = None
        self.physical_angle_var.set(None)
        if self.expert_mode is False:
            self.pixel_length_var.set(None)
            self.physical_length_var.set(None)
            self.pixel_scale_var.set(None)
            self.reference_object.set("Custom")

    @guard_action
    def open_image(self, event: tk.Event | None = None) -> None:
        filename = filedialog.askopenfilename(
            initialdir=self.output_dir,
            title="Select an image",
            filetypes=(
                ("PNG images", "*.png"),
                ("JPEG images", "*.jpg *.jpeg"),
                ("All files", "*.*"),
            ),
        )
        if not filename:
            return
        image = load_image(filename)
        self.reset_state()
        self.img_source = self.img = image
        self.display_type.set(original_image_display_name)
        self.previous_display_type = original_image_display_name
        self.scale = min(
            self.canvas_width / image.width, self.canvas_height / image.height
        )
        self.original_scale = self.scale
        self.noimage_label.pack_forget()
        self.reset_zoom()
        self.status_var.set("Image opened: " + filename)
        self.master.update()

    @guard_action
    def threshold_image(self, event: tk.Event | None = None) -> None:
        if self.img_source is None:
            self.status_var.set("Open an image before thresholding.")
            return
        polygon = (
            None
            if self.polygon_alpha is None
            else np.column_stack((self.polygon_alpha, self.polygon_beta))
        )
        self._threshold = threshold_image(
            np.asarray(self.img_source), self._parameters(), polygon
        )
        self.imdata = self._threshold.blue
        self.background_median = self._threshold.background_median
        self.mask_threshold = self._threshold.indices
        self.mask_threshold_edge = self._threshold.boundary_indices
        self.cluster_data = self.nclusters = None
        self.img_clusters = self.img_histogram = None
        self._clear_statistics()
        display = np.array(self.img_source)
        display[self.mask_threshold] = (255, 0, 0)
        self.img_threshold = Image.fromarray(display)
        self.img = self.img_threshold
        self.display_type.set(threshold_image_display_name)
        self.change_display_type(None)
        fraction = self.mask_threshold[0].size / self.imdata.size * 100
        self.status_var.set(f"Image thresholded: {fraction:.1f}% of pixels selected")

    @guard_action
    def launch_psd(self, event: tk.Event | None = None) -> None:
        if self._threshold is None or self.img_source is None:
            self.status_var.set("Threshold the image before detecting particles.")
            return
        parameters = self._parameters()
        self._busy = True
        controls = self._disable_controls()
        try:
            result = detect_particles(
                np.asarray(self.img_source), self._threshold, parameters, self._progress
            )
        finally:
            self._busy = False
            for control, state in controls:
                control.configure(state=state)
        self.cluster_data = result.clusters
        self.img_histogram = None
        self.refresh_cluster_data()
        self.status_var.set(
            f"Particle detection complete: {result.measurements.count} particles"
        )

    def refresh_cluster_data(self):
        self._set_measurements(self, measurements_from_clusters(self.cluster_data))
        self.img_histogram = None
        self.clusters_xmean = np.array([c["XMEAN"] for c in self.cluster_data])
        self.clusters_ymean = np.array([c["YMEAN"] for c in self.cluster_data])
        imdata_3d = np.array(self.img_source)
        cluster_map_display = np.copy(imdata_3d)
        for i in range(self.nclusters):
            xlist = self.cluster_data[i]["XLIST"]
            ylist = self.cluster_data[i]["YLIST"]
            for pixel in range(xlist.size):
                ineigh = np.where(
                    (np.abs(xlist - xlist[pixel]) <= 1)
                    & (np.abs(ylist - ylist[pixel]) <= 1)
                )
                if ineigh[0].size == 9:
                    continue
                cluster_map_display[xlist[pixel], ylist[pixel], 0] = 255
                cluster_map_display[xlist[pixel], ylist[pixel], 1] = 0
                cluster_map_display[xlist[pixel], ylist[pixel], 2] = 0
            xmean = int(round(self.cluster_data[i]["XMEAN"]))
            ymean = int(round(self.cluster_data[i]["YMEAN"]))
            cluster_map_display[xmean, ymean, 0] = 80
            cluster_map_display[xmean, ymean, 1] = 80
            cluster_map_display[xmean, ymean, 2] = 255
        self.img_clusters = Image.fromarray(cluster_map_display)
        self.display_type.set(outlines_image_display_name)
        self.img = self.img_clusters
        self.update_statistics()
        self.change_display_type()

    def update_statistics(self) -> None:
        if not self.nclusters:
            self._clear_statistics()
            return
        try:
            stats = calculate_statistics(
                self._measurements(self), float(self.pixel_scale_var.get())
            )
        except ValueError, TypeError:
            self._clear_statistics()
            return
        for name, value in stats.legacy_values().items():
            field = {
                "AVG_DIAM": "diam_average_var",
                "STD_DIAM": "diam_stddev_var",
                "AVG_SURF": "surf_average_var",
                "STD_SURF": "surf_stddev_var",
                "EFF": "eff_var",
                "QUAL": "q_var",
            }[name]
            precision = 1 if name == "EFF" else 2
            getattr(self, field).set(f"{value:.{precision}f}")

    @guard_action
    def erase_clusters(self, event):
        if self.cluster_data is None:
            self.status_var.set(
                "Cluster editing requires a detected image, not a loaded CSV."
            )
            return
        if self.nclusters is None:
            self.status_var.set(
                "Coffee Particles not Detected Yet... Use Launch Particle Detection Button..."
            )
            self.master.update()
            return
        if self.display_type.get() != outlines_image_display_name:
            self.status_var.set(
                "Please select 'Display Type' = 'Cluster Outlines' to use the 'Erase Clusters' tool."
            )
            self.master.update()
            return
        if self.erase_clusters_mode is False:
            self.status_var.set(
                "Entered 'Erase Clusters' mode. Click with the mouse to erase all clusters within the circle. Zoom in or out to set precision. Hit Escape or the 'Erase Clusters' button to end."
            )
            self.master.update()
            self.erase_clusters_mode = True
            return
        if self.erase_clusters_mode is True:
            self.status_var.set("The 'Erase Clusters' mode was deactivated.")
            self.master.update()
            self.erase_clusters_mode = False
            return

    @guard_action
    def create_histogram(self, event: tk.Event | None = None) -> None:
        if not self.nclusters:
            self.status_var.set("No particles are available for a histogram.")
            return
        options = HistogramOptions(
            kind=self.histogram_type.get(),
            log=bool(self.xlog_var.get()),
            auto_range=bool(self.xaxis_auto_var.get()),
            minimum=float(self.xmin_var.get())
            if not self.xaxis_auto_var.get()
            else 0.01,
            maximum=float(self.xmax_var.get())
            if not self.xaxis_auto_var.get()
            else 10.0,
            bin_count=None
            if self.nbins_auto_var.get()
            else int(round(float(self.nbins_var.get()))),
        )
        primary = prepare_histogram(
            self._measurements(self), float(self.pixel_scale_var.get()), options
        )
        comparison = None
        if self.comparison.nclusters:
            comparison = prepare_histogram(
                self._measurements(self.comparison),
                float(self.comparison.pixel_scale_var.get()),
                options,
                primary.edges,
            )
        self.img_histogram = render_histogram(
            primary,
            width=self.canvas_width,
            height=self.canvas_height,
            log=options.log,
            label=self.data_label_var.get(),
            comparison=comparison,
            comparison_label=self.comparison_data_label_var.get(),
            legend=self.legend_type.get(),
        )
        self.erase_clusters_mode = False
        self.display_type.set(histogram_image_display_name)
        self.change_display_type(None)
        self.status_var.set("Histogram image is now displayed")

    @guard_action
    def load_data(self, event: tk.Event | None = None) -> None:
        filename = filedialog.askopenfilename(
            initialdir=self.output_dir,
            title="Select a particle CSV",
            filetypes=(("CSV files", "*.csv"),),
        )
        if not filename:
            return
        data, scale = read_measurements(filename)
        self._set_measurements(self, data)
        self.cluster_data = self.img_clusters = self.img_histogram = None
        self.pixel_scale_var.set(str(scale))
        self.update_statistics()
        self.create_histogram(None)

    @guard_action
    def load_comparison_data(self, event: tk.Event | None = None) -> None:
        filename = filedialog.askopenfilename(
            initialdir=self.output_dir,
            title="Select a comparison CSV",
            filetypes=(("CSV files", "*.csv"),),
        )
        if not filename:
            return
        data, scale = read_measurements(filename)
        self._set_measurements(self.comparison, data)
        self.comparison.pixel_scale_var.set(str(scale))
        self.comparison_data_label_id.configure(state=tk.NORMAL)
        self.simple_comparison_data_label_id.configure(state=tk.NORMAL)
        if self.img_histogram is not None:
            self.create_histogram(None)
        self.status_var.set("Comparison data loaded")

    @guard_action
    def flush_comparison_data(self):
        self.comparison.clusters_surface = None
        self.comparison.clusters_roundness = None
        self.comparison.clusters_long_axis = None
        self.comparison.clusters_short_axis = None
        self.comparison.clusters_volume = None
        self.comparison.nclusters = None
        self.comparison.pixel_scale_var.set("None")
        self.comparison_data_label_id.config(state=tk.DISABLED)
        self.simple_comparison_data_label_id.config(state=tk.DISABLED)
        if self.img_histogram is not None:
            self.create_histogram(None)
        self.status_var.set("Comparison Data Flushed from Memory...")

    @guard_action
    def save_data(self, event: tk.Event | None = None) -> None:
        if not self.nclusters:
            self.status_var.set("No particles are available to save.")
            return
        scale = validate_scale(float(self.pixel_scale_var.get()))
        filename = self.session_name_var.get() + "_data.csv"
        destination = (
            os.path.join(self.output_dir, filename)
            if self.expert_mode
            else filedialog.asksaveasfilename(
                initialdir=self.output_dir,
                initialfile=filename,
                defaultextension=".csv",
                title="Save particle data",
            )
        )
        if not destination:
            return
        write_measurements(destination, self._measurements(self), scale)
        self.status_var.set("Data saved to " + destination)

    @guard_action
    def save_histogram(self, event):
        if self.img is None:
            self.status_var.set("No View Created Yet...")
            self.master.update()
            return
        self.status_var.set("Saving View...")
        self.master.update()
        image_code = ""
        if self.display_type.get() == original_image_display_name:
            image_code = "source_image"
        if self.display_type.get() == threshold_image_display_name:
            image_code = "threshold_image"
        if self.display_type.get() == outlines_image_display_name:
            image_code = "outlines_image"
        if self.display_type.get() == histogram_image_display_name:
            ihist = np.where(np.array(self.hist_choices) == self.histogram_type.get())
            image_code = self.hist_codes[ihist[0][0]]
        filename = self.session_name_var.get() + "_hist_" + image_code + ".png"
        if self.expert_mode is True:
            full_filename = self.output_dir + os.sep + filename
        else:
            full_filename = filedialog.asksaveasfilename(
                initialdir=self.output_dir,
                initialfile=filename,
                title="Select an output file name",
            )
        if not full_filename:
            return
        self.img.save(full_filename, format="PNG")
        self.status_var.set("Current View Saved to " + filename + "...")
        self.master.update()

    @guard_action
    def reset_gui(self) -> None:
        for child in self.master.winfo_children():
            child.destroy()
        self.__init__(self.master)

    @guard_action
    def quit_gui(self) -> None:
        self.master.destroy()

    def launch_help(self) -> None:
        webbrowser.open("https://github.com/ischeinfeld/coffeegrindsize#using-the-app")

    def _parameters(self) -> AnalysisParameters:
        return AnalysisParameters(
            threshold=float(self.threshold_var.get()),
            max_cluster_axis=float(self.max_cluster_axis_var.get()),
            min_surface=float(self.min_surface_var.get()),
            min_roundness=float(self.min_roundness_var.get()),
            reference_threshold=float(self.reference_threshold_var.get()),
            maxcost=float(self.maxcost_var.get()),
            quick=bool(self.quick_var.get()),
        )

    @staticmethod
    def _measurements(source: CoffeeGrindSizeApp | ComparisonState) -> Measurements:
        return Measurements(
            source.clusters_surface,
            source.clusters_roundness,
            source.clusters_short_axis,
            source.clusters_long_axis,
            source.clusters_volume,
        )

    @staticmethod
    def _set_measurements(
        source: CoffeeGrindSizeApp | ComparisonState, data: Measurements
    ) -> None:
        source.clusters_surface = data.surface
        source.clusters_roundness = data.roundness
        source.clusters_short_axis = data.short_axis
        source.clusters_long_axis = data.long_axis
        source.clusters_volume = data.volume
        source.nclusters = data.count

    def _clear_statistics(self) -> None:
        for field in (
            "diam_average_var",
            "diam_stddev_var",
            "surf_average_var",
            "surf_stddev_var",
            "eff_var",
            "q_var",
        ):
            getattr(self, field).set("nan")

    def _progress(self, message: str) -> None:
        self.status_var.set(message)
        self.master.update()

    def _disable_controls(self) -> list[tuple[tk.Widget, str]]:
        controls = []

        def visit(widget: tk.Widget) -> None:
            for child in widget.winfo_children():
                if isinstance(
                    child, (tk.Button, tk.Checkbutton, tk.Entry, tk.Menubutton)
                ):
                    controls.append((child, child.cget("state")))
                    child.configure(state=tk.DISABLED)
                visit(child)

        visit(self.master)
        return controls


def main() -> None:
    """Launch one explicit Tk application."""
    root = tk.Tk()
    app = CoffeeGrindSizeApp(root)
    root.protocol("WM_DELETE_WINDOW", app.quit_gui)
    try:
        root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
