"""Tkinter GUI for slm_toolbox — build layered/hybrid SLM phase patterns
interactively.

Add one or more phase-structure layers (vortex, blazed grating, Fresnel lens,
axicon, LG mode, Zernike term, checkerboard, random). All enabled layers are
summed together (the same additive-overlay composition as
slm_toolbox.compose.sum_phases) and wrapped to [0, 2*pi) for preview/export —
so a "vortex + grating" fork hologram, a "vortex + lens + grating" focused
steered OAM beam, etc. are all just multiple layers in the same list.

Run via run_gui.bat, or directly: python phase_gui.py
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as np
from PIL import Image, ImageTk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slm_toolbox import (patterns, compose, render, display, calibration, calibration_patterns,
                         feedback, autocalibrate)

CALIBRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrations")

PATTERN_FIELDS = {
    "Vortex": [("l", int, 3)],
    "Blazed Grating": [("period_px", float, 12.0), ("angle_deg", float, 0.0)],
    "Fresnel Lens": [("focal_length_mm", float, 500.0), ("converging", bool, True)],
    "Beam Position (steer to X,Y)": [("dx_um", float, 0.0), ("dy_um", float, 0.0),
                                      ("focal_length_mm", float, 500.0)],
    "Axicon": [("cone_angle_mdeg", float, 500.0), ("negative", bool, False)],
    "LG Mode": [("p", int, 0), ("l", int, 5), ("z_mm", float, 0.0)],
    "Zernike Term": [("n", int, 2), ("m", int, 2), ("weight_rad", float, 1.0), ("radius_px", float, 200.0)],
    "Checkerboard": [("period_px", float, 16.0), ("low", float, 0.0), ("high", float, 3.14159)],
    "Random": [("seed", int, 0)],
}

# Pattern types with no meaningful spatial center (a per-pixel-independent
# random draw) -- excluded from the center-offset plumbing below.
NO_CENTER_TYPES = {"Random"}

PREVIEW_SIZE = 480


def effective_center(shape, layer, globals_):
    """Global center offset (Global parameters panel) plus this layer's own
    offset on top of it -- both in pixels from the array's true geometric
    center. Returns None (meaning 'use the geometric center exactly') only
    when both are exactly zero, so the common case doesn't pay for it."""
    h, w = shape
    cx = globals_.get("center_x_px", 0.0) + layer.get("center_x", 0.0)
    cy = globals_.get("center_y_px", 0.0) + layer.get("center_y", 0.0)
    if cx == 0.0 and cy == 0.0:
        return None
    return ((w - 1) / 2.0 + cx, (h - 1) / 2.0 + cy)


def layer_phase(shape, layer, globals_):
    t = layer["type"]
    p = layer["params"]
    center = None if t in NO_CENTER_TYPES else effective_center(shape, layer, globals_)

    if t == "Vortex":
        phase = patterns.vortex_phase(shape, l=p["l"], center=center)
    elif t == "Blazed Grating":
        phase = patterns.blazed_grating_phase(shape, period_px=p["period_px"], angle_deg=p["angle_deg"],
                                               center=center)
    elif t == "Fresnel Lens":
        phase = patterns.fresnel_lens_phase(
            shape, focal_length_m=p["focal_length_mm"] * 1e-3,
            wavelength_m=globals_["wavelength_m"], pixel_pitch_m=globals_["pixel_pitch_m"],
            converging=p["converging"], center=center,
        )
    elif t == "Beam Position (steer to X,Y)":
        phase = patterns.beam_position_phase(
            shape, dx_m=p["dx_um"] * 1e-6, dy_m=p["dy_um"] * 1e-6,
            focal_length_m=p["focal_length_mm"] * 1e-3,
            wavelength_m=globals_["wavelength_m"], pixel_pitch_m=globals_["pixel_pitch_m"], center=center,
        )
    elif t == "Axicon":
        phase = patterns.axicon_phase(
            shape, cone_angle_rad=np.deg2rad(p["cone_angle_mdeg"] / 1000.0),
            wavelength_m=globals_["wavelength_m"], pixel_pitch_m=globals_["pixel_pitch_m"],
            sign=-1.0 if p["negative"] else 1.0, center=center,
        )
    elif t == "LG Mode":
        field = patterns.lg_mode_field(
            shape, p=p["p"], l=p["l"], w0_m=globals_["waist_m"],
            wavelength_m=globals_["wavelength_m"], pixel_pitch_m=globals_["pixel_pitch_m"],
            z_m=p["z_mm"] * 1e-3, center=center,
        )
        phase = np.angle(field)
    elif t == "Zernike Term":
        phase = patterns.zernike_phase(shape, coeffs={(p["n"], p["m"]): p["weight_rad"]}, radius_px=p["radius_px"],
                                        center=center)
    elif t == "Checkerboard":
        phase = patterns.checkerboard_phase(shape, period_px=p["period_px"], low=p["low"], high=p["high"],
                                             center=center)
    elif t == "Random":
        phase = patterns.random_phase(shape, seed=p["seed"])
    else:
        raise ValueError(f"unknown pattern type {t!r}")
    return phase * layer.get("weight", 1.0)


def compose_phase(shape, layers, globals_):
    enabled = [l for l in layers if l.get("enabled", True)]
    if not enabled:
        return np.zeros(shape, dtype=np.float64)
    return compose.sum_phases(*[layer_phase(shape, l, globals_) for l in enabled])


class PhaseGeneratorApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.master = master
        self.master.title("SLM Phase Generator")
        self.layers = []
        self.field_vars = {}
        self.last_gray = None
        self.preview_photo = None
        self.monitors = []
        self.projector = None
        self.cal_library = calibration.CalibrationLibrary(CALIBRATIONS_DIR)
        self.camera = None
        self.camera_photo = None
        self._last_phase = None   # wrapped phase last rendered; read by feedback loops

        self.pack(fill="both", expand=True)
        self._build_globals()
        self._build_layer_list()
        self._build_editor()
        self._build_preview()
        self._build_projection()
        self._build_calibration()
        self._build_camera()

        self.master.protocol("WM_DELETE_WINDOW", self._on_close)

        self._select_type("Vortex")

        # Seed with a default vortex+grating fork hologram so there's
        # something on screen immediately.
        self.layers = [
            {"type": "Vortex", "params": {"l": 3}, "weight": 1.0, "enabled": True},
            {"type": "Blazed Grating", "params": {"period_px": 12.0, "angle_deg": 0.0}, "weight": 1.0, "enabled": True},
        ]
        self._refresh_listbox()
        self._generate_preview()

    # ---------- global params ----------
    def _build_globals(self):
        box = ttk.LabelFrame(self, text="Global parameters")
        box.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        self.g_width = tk.StringVar(value=str(display.DEFAULT_SLM_WIDTH))
        self.g_height = tk.StringVar(value=str(display.DEFAULT_SLM_HEIGHT))
        self.g_wavelength_nm = tk.StringVar(value="1064")
        self.g_pixel_pitch_um = tk.StringVar(value="8.0")
        self.g_waist_um = tk.StringVar(value="40.0")
        self.g_bit_depth = tk.StringVar(value="8")

        entries = [
            ("Width (px)", self.g_width), ("Height (px)", self.g_height),
            ("Wavelength (nm)", self.g_wavelength_nm), ("Pixel pitch (um)", self.g_pixel_pitch_um),
            ("Waist w0 (um)", self.g_waist_um),
        ]
        for i, (label, var) in enumerate(entries):
            ttk.Label(box, text=label).grid(row=0, column=2 * i, sticky="e", padx=4, pady=2)
            ttk.Entry(box, textvariable=var, width=8).grid(row=0, column=2 * i + 1, sticky="w", padx=4, pady=2)

        ttk.Label(box, text="Bit depth").grid(row=0, column=10, sticky="e", padx=4)
        ttk.Combobox(box, textvariable=self.g_bit_depth, values=["8", "16"], width=4, state="readonly").grid(
            row=0, column=11, sticky="w", padx=4)

        self.g_center_x = tk.StringVar(value="0")
        self.g_center_y = tk.StringVar(value="0")
        ttk.Label(box, text="Center X (px)").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(box, textvariable=self.g_center_x, width=8).grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(box, text="Center Y (px)").grid(row=1, column=2, sticky="e", padx=4, pady=2)
        ttk.Entry(box, textvariable=self.g_center_y, width=8).grid(row=1, column=3, sticky="w", padx=4, pady=2)
        ttk.Label(box, text="(offsets the whole pattern from the frame's geometric center; "
                             "each layer can offset further on top of this)",
                  foreground="#666666").grid(row=1, column=4, columnspan=6, sticky="w", padx=4, pady=2)

    def _globals(self):
        return {
            "wavelength_m": float(self.g_wavelength_nm.get()) * 1e-9,
            "pixel_pitch_m": float(self.g_pixel_pitch_um.get()) * 1e-6,
            "waist_m": float(self.g_waist_um.get()) * 1e-6,
            "center_x_px": float(self.g_center_x.get()),
            "center_y_px": float(self.g_center_y.get()),
        }

    def _shape(self):
        return (int(self.g_height.get()), int(self.g_width.get()))

    # ---------- layer list ----------
    def _build_layer_list(self):
        box = ttk.LabelFrame(self, text="Layers (summed together)")
        box.grid(row=1, column=0, sticky="ns", padx=(0, 8))

        self.listbox = tk.Listbox(box, width=30, height=14, exportselection=False)
        self.listbox.pack(side="top", fill="both", expand=True, padx=4, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self._on_select_layer)

        btns = ttk.Frame(box)
        btns.pack(side="top", fill="x", padx=4, pady=(0, 4))
        ttk.Button(btns, text="Remove", command=self._remove_layer).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Toggle On/Off", command=self._toggle_layer).pack(side="left", expand=True, fill="x")

        move = ttk.Frame(box)
        move.pack(side="top", fill="x", padx=4, pady=(0, 4))
        ttk.Button(move, text="Move Up", command=lambda: self._move_layer(-1)).pack(side="left", expand=True, fill="x")
        ttk.Button(move, text="Move Down", command=lambda: self._move_layer(1)).pack(side="left", expand=True, fill="x")

    def _refresh_listbox(self):
        self.listbox.delete(0, "end")
        for layer in self.layers:
            mark = "" if layer.get("enabled", True) else "(off) "
            cx, cy = layer.get("center_x", 0.0), layer.get("center_y", 0.0)
            offset_str = f"  @({cx:g},{cy:g})" if (cx, cy) != (0.0, 0.0) else ""
            self.listbox.insert("end", f"{mark}{layer['type']}  w={layer.get('weight', 1.0):g}{offset_str}")

    def _selected_index(self):
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _on_select_layer(self, _event=None):
        idx = self._selected_index()
        if idx is None:
            return
        layer = self.layers[idx]
        self.type_var.set(layer["type"])
        self._build_fields(layer["type"])
        for name, var in self.field_vars.items():
            if name in layer["params"]:
                var.set(layer["params"][name])
        self.weight_var.set(str(layer.get("weight", 1.0)))
        self.layer_center_x_var.set(str(layer.get("center_x", 0.0)))
        self.layer_center_y_var.set(str(layer.get("center_y", 0.0)))

    def _remove_layer(self):
        idx = self._selected_index()
        if idx is None:
            return
        del self.layers[idx]
        self._refresh_listbox()

    def _toggle_layer(self):
        idx = self._selected_index()
        if idx is None:
            return
        self.layers[idx]["enabled"] = not self.layers[idx].get("enabled", True)
        self._refresh_listbox()
        self.listbox.selection_set(idx)

    def _move_layer(self, delta):
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + delta
        if not (0 <= new_idx < len(self.layers)):
            return
        self.layers[idx], self.layers[new_idx] = self.layers[new_idx], self.layers[idx]
        self._refresh_listbox()
        self.listbox.selection_set(new_idx)

    # ---------- layer editor ----------
    def _build_editor(self):
        box = ttk.LabelFrame(self, text="Layer editor")
        box.grid(row=1, column=1, sticky="n", padx=(0, 8))

        self.type_var = tk.StringVar(value="Vortex")
        type_row = ttk.Frame(box)
        type_row.pack(side="top", fill="x", padx=4, pady=4)
        ttk.Label(type_row, text="Pattern type").pack(side="left")
        combo = ttk.Combobox(type_row, textvariable=self.type_var, values=list(PATTERN_FIELDS.keys()),
                              state="readonly", width=18)
        combo.pack(side="left", padx=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._select_type(self.type_var.get()))

        self.fields_frame = ttk.Frame(box)
        self.fields_frame.pack(side="top", fill="x", padx=4, pady=4)

        weight_row = ttk.Frame(box)
        weight_row.pack(side="top", fill="x", padx=4, pady=4)
        ttk.Label(weight_row, text="Weight (multiplier)").pack(side="left")
        self.weight_var = tk.StringVar(value="1.0")
        ttk.Entry(weight_row, textvariable=self.weight_var, width=8).pack(side="left", padx=4)

        center_row = ttk.Frame(box)
        center_row.pack(side="top", fill="x", padx=4, pady=4)
        ttk.Label(center_row, text="Center offset X,Y (px)").pack(side="left")
        self.layer_center_x_var = tk.StringVar(value="0")
        ttk.Entry(center_row, textvariable=self.layer_center_x_var, width=6).pack(side="left", padx=4)
        self.layer_center_y_var = tk.StringVar(value="0")
        ttk.Entry(center_row, textvariable=self.layer_center_y_var, width=6).pack(side="left", padx=4)
        ttk.Label(center_row, text="(added on top of the global Center X,Y)",
                  foreground="#666666").pack(side="left", padx=4)

        btns = ttk.Frame(box)
        btns.pack(side="top", fill="x", padx=4, pady=8)
        ttk.Button(btns, text="Add Layer", command=self._add_layer).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Apply to Selected", command=self._apply_layer).pack(side="left", expand=True, fill="x")

    def _select_type(self, type_name):
        self.type_var.set(type_name)
        self._build_fields(type_name)

    def _build_fields(self, type_name):
        for child in self.fields_frame.winfo_children():
            child.destroy()
        self.field_vars = {}
        for row, (name, kind, default) in enumerate(PATTERN_FIELDS[type_name]):
            ttk.Label(self.fields_frame, text=name).grid(row=row, column=0, sticky="e", padx=4, pady=2)
            if kind is bool:
                var = tk.BooleanVar(value=default)
                ttk.Checkbutton(self.fields_frame, variable=var).grid(row=row, column=1, sticky="w", padx=4, pady=2)
            else:
                var = tk.StringVar(value=str(default))
                ttk.Entry(self.fields_frame, textvariable=var, width=12).grid(row=row, column=1, sticky="w", padx=4, pady=2)
            self.field_vars[name] = var

    def _read_editor_params(self):
        type_name = self.type_var.get()
        params = {}
        for name, kind, _default in PATTERN_FIELDS[type_name]:
            var = self.field_vars[name]
            if kind is bool:
                params[name] = bool(var.get())
            elif kind is int:
                params[name] = int(float(var.get()))
            else:
                params[name] = float(var.get())
        return type_name, params

    def _read_editor_center(self):
        return float(self.layer_center_x_var.get()), float(self.layer_center_y_var.get())

    def _add_layer(self):
        try:
            type_name, params = self._read_editor_params()
            weight = float(self.weight_var.get())
            center_x, center_y = self._read_editor_center()
        except ValueError as exc:
            messagebox.showerror("Invalid parameter", str(exc))
            return
        self.layers.append({"type": type_name, "params": params, "weight": weight, "enabled": True,
                             "center_x": center_x, "center_y": center_y})
        self._refresh_listbox()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(len(self.layers) - 1)

    def _apply_layer(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("No layer selected", "Select a layer in the list first, or use Add Layer.")
            return
        try:
            type_name, params = self._read_editor_params()
            weight = float(self.weight_var.get())
            center_x, center_y = self._read_editor_center()
        except ValueError as exc:
            messagebox.showerror("Invalid parameter", str(exc))
            return
        self.layers[idx] = {"type": type_name, "params": params, "weight": weight,
                             "enabled": self.layers[idx].get("enabled", True),
                             "center_x": center_x, "center_y": center_y}
        self._refresh_listbox()
        self.listbox.selection_set(idx)

    # ---------- preview ----------
    def _build_preview(self):
        box = ttk.LabelFrame(self, text="Preview")
        box.grid(row=1, column=2, sticky="n")

        self.preview_label = ttk.Label(box)
        self.preview_label.pack(padx=4, pady=4)

        btns = ttk.Frame(box)
        btns.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(btns, text="Generate Preview", command=self._generate_preview).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Save Pattern...", command=self._save_pattern).pack(side="left", expand=True, fill="x")

        btns2 = ttk.Frame(box)
        btns2.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(btns2, text="View Full-Resolution...", command=self._view_full_resolution).pack(
            side="left", expand=True, fill="x")

        self.status_var = tk.StringVar(value="No pattern generated yet.")
        ttk.Label(box, textvariable=self.status_var, wraplength=PREVIEW_SIZE).pack(fill="x", padx=4, pady=4)

    def _generate_preview(self):
        try:
            shape = self._shape()
            globals_ = self._globals()
            bit_depth = int(self.g_bit_depth.get())
        except ValueError as exc:
            messagebox.showerror("Invalid global parameter", str(exc))
            return

        try:
            phase = compose_phase(shape, self.layers, globals_)
        except (ValueError, ZeroDivisionError) as exc:
            messagebox.showerror("Could not generate pattern", str(exc))
            return

        wavelength_nm = float(self.g_wavelength_nm.get())
        curve, cal_msg = self.cal_library.resolve(wavelength_nm, bit_depth=bit_depth)
        self.calibration_status_var.set(cal_msg)
        gamma_lut = curve.to_gamma_lut()

        wrapped = compose.wrap_phase(phase)
        self._last_phase = wrapped   # so a connected feedback camera images the current pattern
        gray = render.phase_to_gray(wrapped, bit_depth=bit_depth, gamma_lut=gamma_lut)
        self.last_gray = gray

        preview_src = gray if gray.dtype == np.uint8 else (gray >> (bit_depth - 8)).astype(np.uint8)
        img = Image.fromarray(preview_src, mode="L")
        img.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(img, master=self.master)
        self.preview_label.configure(image=self.preview_photo)

        n_enabled = sum(1 for l in self.layers if l.get("enabled", True))
        self.status_var.set(f"{shape[1]}x{shape[0]} px, {n_enabled} active layer(s), {bit_depth}-bit.")

    def _save_pattern(self):
        if self.last_gray is None:
            messagebox.showinfo("Nothing to save", "Click Generate Preview first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("BMP", "*.bmp"), ("All files", "*.*")],
        )
        if not path:
            return
        render.save_pattern(path, self.last_gray)
        self.status_var.set(f"Saved to {path}")

    def _view_full_resolution(self):
        """Open the pattern at its true native resolution (no resampling) in
        an ordinary, resizable/scrollable window on whichever monitor this
        opens on -- for pixel-perfect inspection without needing the SLM
        connected. To actually send it to the SLM, use the Projection panel
        below (a borderless window pinned to the SLM's monitor)."""
        if self.last_gray is None:
            messagebox.showinfo("Nothing to preview", "Click Generate Preview first.")
            return

        h, w = self.last_gray.shape
        top = tk.Toplevel(self.master)
        top.title(f"Full-Resolution Preview ({w}x{h}, no resampling)")

        mode = "L" if self.last_gray.dtype == np.uint8 else "I;16"
        image = Image.fromarray(self.last_gray, mode=mode)
        photo = ImageTk.PhotoImage(image)
        top._photo = photo  # keep a reference so it isn't garbage-collected

        max_w = max(400, top.winfo_screenwidth() - 100)
        max_h = max(300, top.winfo_screenheight() - 150)
        canvas = tk.Canvas(top, width=min(w, max_w), height=min(h, max_h), bg="black",
                            highlightthickness=0)
        vbar = ttk.Scrollbar(top, orient="vertical", command=canvas.yview)
        hbar = ttk.Scrollbar(top, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set, scrollregion=(0, 0, w, h))
        canvas.create_image(0, 0, anchor="nw", image=photo)

        canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        top.grid_rowconfigure(0, weight=1)
        top.grid_columnconfigure(0, weight=1)

    # ---------- projection (send to SLM over HDMI) ----------
    def _build_projection(self):
        box = ttk.LabelFrame(self, text="Projection (send to SLM over HDMI)")
        box.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        ttk.Label(box, text="Target monitor").pack(side="left", padx=4, pady=4)
        self.monitor_var = tk.StringVar()
        self.monitor_combo = ttk.Combobox(box, textvariable=self.monitor_var, state="readonly", width=32)
        self.monitor_combo.pack(side="left", padx=4, pady=4)

        ttk.Button(box, text="Refresh Monitors", command=self._refresh_monitors).pack(side="left", padx=4, pady=4)
        ttk.Button(box, text="Project to Monitor", command=self._project_pattern).pack(side="left", padx=4, pady=4)
        ttk.Button(box, text="Stop Projecting", command=self._stop_projecting).pack(side="left", padx=4, pady=4)

        self.projection_status_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.projection_status_var).pack(side="left", padx=8, pady=4)

        self._refresh_monitors()

    def _refresh_monitors(self):
        self.monitors = display.list_monitors()
        labels = [
            f"{i}: {m['width']}x{m['height']} @ ({m['x']},{m['y']})" + (" [Primary]" if m["primary"] else "")
            for i, m in enumerate(self.monitors)
        ]
        self.monitor_combo["values"] = labels
        if not labels:
            self.monitor_var.set("")
            return
        target = display.default_slm_monitor(self.monitors)
        default_idx = self.monitors.index(target) if target in self.monitors else 0
        self.monitor_var.set(labels[default_idx])

    def _selected_monitor(self):
        val = self.monitor_var.get()
        if not val:
            return None
        idx = int(val.split(":", 1)[0])
        return self.monitors[idx]

    def _project_pattern(self):
        if self.last_gray is None:
            messagebox.showinfo("Nothing to project", "Click Generate Preview first.")
            return
        monitor = self._selected_monitor()
        if monitor is None:
            messagebox.showerror("No monitor selected", "Click Refresh Monitors and select a target display.")
            return

        h, w = self.last_gray.shape
        if (w, h) != (monitor["width"], monitor["height"]):
            proceed = messagebox.askyesno(
                "Resolution mismatch",
                f"Pattern is {w}x{h} but the selected monitor is "
                f"{monitor['width']}x{monitor['height']}. The pattern will NOT be resized "
                "(resizing would interpolate phase values and corrupt the hologram), so it "
                "will only fill part of the screen.\n\n"
                "Set Width/Height to match the SLM's native resolution and re-generate for "
                "correct output. Project anyway?",
            )
            if not proceed:
                return

        if self.projector is not None:
            self.projector.close()
        self.projector = display.ProjectorWindow(self.master, monitor, self.last_gray,
                                                   on_close=self._on_projector_closed)
        self.projection_status_var.set(f"Projecting on monitor at ({monitor['x']},{monitor['y']}).")

    def _on_projector_closed(self):
        self.projector = None
        self.projection_status_var.set("")

    def _stop_projecting(self):
        if self.projector is not None:
            self.projector.close()

    # ---------- calibration (wavelength -> gray/gamma LUT) ----------
    def _build_calibration(self):
        box = ttk.LabelFrame(self, text="Calibration (gray level <-> phase, per wavelength)")
        box.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        row1 = ttk.Frame(box)
        row1.pack(fill="x")
        ttk.Button(row1, text="Enter/Edit Calibration...", command=self._open_calibration_dialog).pack(
            side="left", padx=4, pady=4)
        ttk.Button(row1, text="Load Calibration File...", command=self._load_calibration_file).pack(
            side="left", padx=4, pady=4)
        ttk.Button(row1, text="Reload Calibrations", command=self._reload_calibrations).pack(
            side="left", padx=4, pady=4)

        row2 = ttk.Frame(box)
        row2.pack(fill="x")
        ttk.Button(row2, text="Calibration Wizard (Method C)...", command=self._open_calibration_wizard).pack(
            side="left", padx=4, pady=4)
        ttk.Button(row2, text="Self-Referenced Pattern (Method A)...",
                   command=self._open_self_referenced_dialog).pack(side="left", padx=4, pady=4)

        self.calibration_status_var = tk.StringVar(
            value=f"No calibration checked yet -- click Generate Preview. Files load from {CALIBRATIONS_DIR}")
        ttk.Label(box, textvariable=self.calibration_status_var, wraplength=900).pack(
            fill="x", padx=8, pady=4)

    def _reload_calibrations(self):
        # CalibrationLibrary re-scans its directory on every resolve() call,
        # so this just re-runs the resolution for the current wavelength.
        self._generate_preview()

    def _load_calibration_file(self):
        path = filedialog.askopenfilename(filetypes=[("Calibration JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            curve = calibration.CalibrationCurve.load(path)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Could not load calibration", str(exc))
            return
        os.makedirs(CALIBRATIONS_DIR, exist_ok=True)
        self.cal_library.save(curve)
        messagebox.showinfo("Calibration loaded", f"Saved as the calibration for {curve.wavelength_nm}nm.")
        self._generate_preview()

    def _open_calibration_dialog(self):
        try:
            wavelength_nm = float(self.g_wavelength_nm.get())
        except ValueError:
            messagebox.showerror("Invalid wavelength", "Set a valid Wavelength (nm) first.")
            return

        top = tk.Toplevel(self.master)
        top.title(f"Calibration for {wavelength_nm:g}nm")
        top.geometry("480x420")

        ttk.Label(
            top,
            text=(
                f"Measured gray-level -> phase points for {wavelength_nm:g}nm, one 'gray,phase_rad' pair "
                "per line. Phase must be non-decreasing and should span 0 to 2*pi (~6.283) somewhere in "
                "the range. See calibration_SOP.md for how to measure these."
            ),
            wraplength=460, justify="left",
        ).pack(fill="x", padx=8, pady=8)

        text = tk.Text(top, height=16)
        text.pack(fill="both", expand=True, padx=8, pady=4)

        existing, _msg = self.cal_library.resolve(wavelength_nm, tolerance_nm=0.5)
        if existing.source not in ("uncalibrated-linear",) and abs(existing.wavelength_nm - wavelength_nm) < 0.5:
            lines = "\n".join(f"{g:g},{p:.6f}" for g, p in zip(existing.gray, existing.phase_rad))
            text.insert("1.0", lines)
        else:
            text.insert("1.0", "0,0.0\n255,6.283185307\n")

        status_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=status_var, wraplength=460).pack(fill="x", padx=8, pady=4)

        def do_save():
            gray_list, phase_list = [], []
            for lineno, line in enumerate(text.get("1.0", "end").splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                parts = line.replace("\t", ",").split(",")
                if len(parts) != 2:
                    status_var.set(f"Line {lineno}: expected 'gray,phase_rad', got {line!r}")
                    return
                try:
                    gray_list.append(float(parts[0]))
                    phase_list.append(float(parts[1]))
                except ValueError:
                    status_var.set(f"Line {lineno}: could not parse numbers in {line!r}")
                    return
            if len(gray_list) < 2:
                status_var.set("Need at least 2 points.")
                return
            try:
                curve = calibration.CalibrationCurve(wavelength_nm, gray_list, phase_list)
            except ValueError as exc:
                status_var.set(str(exc))
                return
            os.makedirs(CALIBRATIONS_DIR, exist_ok=True)
            self.cal_library.save(curve)
            top.destroy()
            messagebox.showinfo("Calibration saved", f"Saved calibration for {wavelength_nm:g}nm.")
            self._generate_preview()

        btns = ttk.Frame(top)
        btns.pack(fill="x", padx=8, pady=8)
        ttk.Button(btns, text="Save", command=do_save).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Cancel", command=top.destroy).pack(side="left", expand=True, fill="x")

    def _open_calibration_wizard(self):
        """Method C (calibration_SOP.md): step through a gray-level sweep,
        project a reference-vs-test two-level grating for each, record the
        measured 1st-order diffraction efficiency, then invert the whole
        sweep into a calibration curve."""
        try:
            wavelength_nm = float(self.g_wavelength_nm.get())
        except ValueError:
            messagebox.showerror("Invalid wavelength", "Set a valid Wavelength (nm) first.")
            return

        top = tk.Toplevel(self.master)
        top.title(f"Calibration Wizard -- Method C ({wavelength_nm:g}nm)")

        ttk.Label(
            top,
            text=(
                "Method C: two-level grating diffraction efficiency (calibration_SOP.md). For each "
                "gray level below: pick a target monitor in the Projection panel, select the level "
                "here, click 'Project This Level' (alternates the reference gray and that test gray "
                "as stripes), measure 1st-order diffraction efficiency with a power meter/camera, "
                "type it in, click 'Record'. Once every level has a value, click 'Compute & Save' -- "
                "needs the efficiency to visibly rise then fall across the sweep (i.e. actually pass "
                "through a phase difference of pi) to invert correctly."
            ),
            wraplength=520, justify="left",
        ).pack(fill="x", padx=8, pady=8)

        params = ttk.Frame(top)
        params.pack(fill="x", padx=8, pady=4)
        ttk.Label(params, text="Grating period (px)").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        period_var = tk.StringVar(value="20")
        ttk.Entry(params, textvariable=period_var, width=8).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(params, text="Reference gray").grid(row=0, column=2, sticky="e", padx=4, pady=2)
        ref_var = tk.StringVar(value="0")
        ttk.Entry(params, textvariable=ref_var, width=8).grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(params, text="Sweep start,stop,count").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        sweep_var = tk.StringVar(value="0,255,17")
        ttk.Entry(params, textvariable=sweep_var, width=14).grid(row=1, column=1, padx=4, pady=2)

        body = ttk.Frame(top)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        listbox = tk.Listbox(body, height=14, width=40, exportselection=False)
        listbox.pack(side="left", fill="both", expand=True)
        list_scroll = ttk.Scrollbar(body, command=listbox.yview)
        list_scroll.pack(side="left", fill="y")
        listbox.configure(yscrollcommand=list_scroll.set)

        rows = []

        def refresh_listbox():
            listbox.delete(0, "end")
            for r in rows:
                eff_str = f"{r['efficiency']:.4g}" if r["efficiency"] is not None else "(not measured)"
                listbox.insert("end", f"gray={r['gray']}  efficiency={eff_str}")

        def regenerate():
            try:
                start, stop, count = (float(x) for x in sweep_var.get().split(","))
                count = int(count)
            except ValueError:
                messagebox.showerror("Invalid sweep", "Use 'start,stop,count', e.g. 0,255,17")
                return
            levels = sorted(set(int(round(g)) for g in np.linspace(start, stop, count)))
            rows.clear()
            rows.extend({"gray": g, "efficiency": None} for g in levels)
            refresh_listbox()

        ttk.Button(params, text="Generate Levels", command=regenerate).grid(
            row=1, column=2, columnspan=2, sticky="w", padx=4, pady=2)
        regenerate()

        entry_row = ttk.Frame(top)
        entry_row.pack(fill="x", padx=8, pady=4)
        ttk.Label(entry_row, text="Measured efficiency for selected level:").pack(side="left")
        eff_entry_var = tk.StringVar()
        ttk.Entry(entry_row, textvariable=eff_entry_var, width=12).pack(side="left", padx=4)

        def selected_row_idx():
            sel = listbox.curselection()
            return sel[0] if sel else None

        def project_selected():
            idx = selected_row_idx()
            if idx is None:
                messagebox.showinfo("No level selected", "Select a gray level in the list first.")
                return
            monitor = self._selected_monitor()
            if monitor is None:
                messagebox.showerror("No monitor selected", "Pick a target monitor in the Projection panel first.")
                return
            try:
                period_px = float(period_var.get())
                g_ref = int(ref_var.get())
            except ValueError:
                messagebox.showerror("Invalid parameter", "Grating period / reference gray must be numeric.")
                return
            shape = (monitor["height"], monitor["width"])
            pattern = calibration_patterns.two_level_grating_pattern(shape, period_px, g_ref, rows[idx]["gray"])
            if self.projector is not None:
                self.projector.close()
            self.projector = display.ProjectorWindow(self.master, monitor, pattern,
                                                       on_close=self._on_projector_closed)
            self.projection_status_var.set(f"Projecting calibration grating: ref={g_ref}, test={rows[idx]['gray']}.")

        def record_selected():
            idx = selected_row_idx()
            if idx is None:
                messagebox.showinfo("No level selected", "Select a gray level in the list first.")
                return
            try:
                rows[idx]["efficiency"] = float(eff_entry_var.get())
            except ValueError:
                messagebox.showerror("Invalid value", "Enter a numeric efficiency reading.")
                return
            refresh_listbox()
            listbox.selection_set(idx)

        btn_row = ttk.Frame(top)
        btn_row.pack(fill="x", padx=8, pady=4)
        ttk.Button(btn_row, text="Project This Level", command=project_selected).pack(
            side="left", expand=True, fill="x")
        ttk.Button(btn_row, text="Record Efficiency", command=record_selected).pack(
            side="left", expand=True, fill="x")

        def compute_and_save():
            missing = [r["gray"] for r in rows if r["efficiency"] is None]
            if missing:
                messagebox.showerror("Incomplete", f"Missing efficiency for gray levels: {missing}")
                return
            try:
                curve = calibration.CalibrationCurve.from_efficiency_sweep(
                    wavelength_nm, [r["gray"] for r in rows], [r["efficiency"] for r in rows],
                    gray_ref=int(ref_var.get()),
                )
            except ValueError as exc:
                messagebox.showerror("Could not compute calibration", str(exc))
                return
            os.makedirs(CALIBRATIONS_DIR, exist_ok=True)
            self.cal_library.save(curve)
            top.destroy()
            messagebox.showinfo("Calibration saved", f"Saved calibration for {wavelength_nm:g}nm.")
            self._generate_preview()

        ttk.Button(top, text="Compute & Save Calibration", command=compute_and_save).pack(
            fill="x", padx=8, pady=8)

    def _open_self_referenced_dialog(self):
        """Method A (calibration_SOP.md): project the self-referenced
        interferometry base pattern (grating half + uniform piston half) for
        a chosen piston gray level. Phase extraction from the resulting
        fringes depends on your camera/optics setup, so this just displays
        the pattern -- read the phase off your interferogram and enter it via
        'Enter/Edit Calibration...'."""
        top = tk.Toplevel(self.master)
        top.title("Method A: Self-Referenced Interferometry Pattern")

        ttk.Label(
            top,
            text=(
                "Displays a two-region pattern: one half a fixed grating (creates a tilted "
                "reference beam via diffraction), the other half a uniform 'piston' gray level "
                "under test. The two interfere downstream with just a collimated beam and a "
                "camera -- no interferometer optics needed. Vary the piston gray level and read "
                "the resulting fringe phase shift off your interferogram; see calibration_SOP.md "
                "Method A. Phase extraction itself is setup-specific and not automated here -- "
                "once you have gray->phase points, enter them via 'Enter/Edit Calibration...'."
            ),
            wraplength=420, justify="left",
        ).pack(fill="x", padx=8, pady=8)

        fields = ttk.Frame(top)
        fields.pack(fill="x", padx=8, pady=4)
        specs = [("Piston gray (test)", "128"), ("Grating gray A", "0"), ("Grating gray B", "255"),
                 ("Grating period (px)", "15"), ("Split fraction", "0.5")]
        vars_ = {}
        for i, (label, default) in enumerate(specs):
            ttk.Label(fields, text=label).grid(row=i, column=0, sticky="e", padx=4, pady=2)
            var = tk.StringVar(value=default)
            ttk.Entry(fields, textvariable=var, width=10).grid(row=i, column=1, sticky="w", padx=4, pady=2)
            vars_[label] = var

        orientation_var = tk.StringVar(value="horizontal")
        ttk.Label(fields, text="Split orientation").grid(row=len(specs), column=0, sticky="e", padx=4, pady=2)
        ttk.Combobox(fields, textvariable=orientation_var, values=["horizontal", "vertical"],
                     state="readonly", width=10).grid(row=len(specs), column=1, sticky="w", padx=4, pady=2)

        def do_project():
            monitor = self._selected_monitor()
            if monitor is None:
                messagebox.showerror("No monitor selected", "Pick a target monitor in the Projection panel first.")
                return
            try:
                piston = int(vars_["Piston gray (test)"].get())
                ga = int(vars_["Grating gray A"].get())
                gb = int(vars_["Grating gray B"].get())
                period = float(vars_["Grating period (px)"].get())
                split = float(vars_["Split fraction"].get())
            except ValueError:
                messagebox.showerror("Invalid parameter", "All fields must be numeric.")
                return
            shape = (monitor["height"], monitor["width"])
            pattern = calibration_patterns.self_referenced_calibration_pattern(
                shape, piston, ga, gb, period, split_fraction=split, orientation=orientation_var.get())
            if self.projector is not None:
                self.projector.close()
            self.projector = display.ProjectorWindow(self.master, monitor, pattern,
                                                       on_close=self._on_projector_closed)
            self.projection_status_var.set(f"Projecting self-referenced calibration pattern (piston={piston}).")

        ttk.Button(top, text="Project Pattern", command=do_project).pack(fill="x", padx=8, pady=8)

    # ---------- camera + self-calibration ----------
    def _build_camera(self):
        box = ttk.LabelFrame(self, text="Camera + self-calibration (image feedback)")
        box.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        row1 = ttk.Frame(box)
        row1.pack(fill="x")
        ttk.Label(row1, text="Source").pack(side="left", padx=4, pady=4)
        self.camera_source_var = tk.StringVar(value="Simulated (no hardware)")
        ttk.Combobox(row1, textvariable=self.camera_source_var,
                     values=["Simulated (no hardware)", "HIKROBOT (MVS SDK)"],
                     state="readonly", width=22).pack(side="left", padx=4, pady=4)
        ttk.Button(row1, text="Connect", command=self._connect_camera).pack(side="left", padx=4, pady=4)
        ttk.Button(row1, text="Grab Frame", command=self._grab_frame).pack(side="left", padx=4, pady=4)
        ttk.Button(row1, text="Self-Calibrate Aberration",
                   command=self._self_calibrate).pack(side="left", padx=4, pady=4)

        row2 = ttk.Frame(box)
        row2.pack(fill="x")
        ttk.Label(row2, text="SPGD iters").pack(side="left", padx=4, pady=4)
        self.spgd_iters_var = tk.StringVar(value="80")
        ttk.Entry(row2, textvariable=self.spgd_iters_var, width=6).pack(side="left", padx=4, pady=4)
        ttk.Label(row2, text="Zernike terms (n,m; ...)").pack(side="left", padx=4, pady=4)
        self.spgd_terms_var = tk.StringVar(value="2,2; 2,-2; 3,1; 3,-1; 2,0")
        ttk.Entry(row2, textvariable=self.spgd_terms_var, width=28).pack(side="left", padx=4, pady=4)

        body = ttk.Frame(box)
        body.pack(fill="x")
        self.camera_label = ttk.Label(body)
        self.camera_label.pack(side="left", padx=4, pady=4)
        self.camera_status_var = tk.StringVar(value="No camera connected.")
        ttk.Label(body, textvariable=self.camera_status_var, wraplength=520,
                  justify="left").pack(side="left", padx=8, pady=4, anchor="n")

    def _connect_camera(self):
        source = self.camera_source_var.get()
        if self.camera is not None:
            try:
                self.camera.close()
            except Exception:
                pass
            self.camera = None
        try:
            if source.startswith("Simulated"):
                from slm_toolbox.instruments import mock
                # A preset "test aberration" only present in the simulated
                # optics, so Self-Calibrate visibly finds and cancels it.
                self._sim_aberration = {(2, 2): 2.0, (3, 1): 1.4, (2, 0): 1.2}
                self.camera = mock.SimFeedbackCamera(
                    self._calibration_slm(), aberration_coeffs=self._sim_aberration,
                    sim_size=96, cam_size=64)
                self.camera_status_var.set(
                    "Simulated camera connected (frames = far-field of the current pattern, with a "
                    "built-in test aberration to correct). Grab Frame or Self-Calibrate.")
            else:
                from slm_toolbox.instruments import HikrobotCamera
                self.camera = HikrobotCamera(device_index=0)
                self._sim_aberration = None
                self.camera_status_var.set("HIKROBOT camera connected. Grab Frame or Self-Calibrate.")
        except Exception as exc:
            messagebox.showerror("Could not connect camera", str(exc))
            self.camera_status_var.set(f"Connect failed: {exc}")
            return
        self._grab_frame()

    def _grab_frame(self):
        if self.camera is None:
            messagebox.showinfo("No camera", "Click Connect first.")
            return
        # Make sure there's a rendered phase for a simulated camera to image.
        if self._last_phase is None:
            self._generate_preview()
        try:
            frame = self.camera.grab()
        except Exception as exc:
            messagebox.showerror("Grab failed", str(exc))
            return
        self._show_camera_frame(frame)
        spot = feedback.find_spot(frame)
        self.camera_status_var.set(
            f"Frame {frame.shape[1]}x{frame.shape[0]}  peak={spot['peak']:.0f}  "
            f"sharpness={feedback.sharpness(frame):.4g}  "
            f"saturated={spot['saturated_fraction']*100:.1f}%")

    def _show_camera_frame(self, frame):
        img = Image.fromarray(frame, mode="L")
        img.thumbnail((240, 240), Image.Resampling.NEAREST)
        self.camera_photo = ImageTk.PhotoImage(img, master=self.master)
        self.camera_label.configure(image=self.camera_photo)

    def _parse_terms(self):
        terms = []
        for chunk in self.spgd_terms_var.get().split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            n, m = (int(x) for x in chunk.split(","))
            terms.append((n, m))
        return terms

    def _self_calibrate(self):
        if self.camera is None:
            messagebox.showinfo("No camera", "Connect a camera first.")
            return
        try:
            n_iter = int(self.spgd_iters_var.get())
            terms = self._parse_terms()
        except ValueError as exc:
            messagebox.showerror("Invalid parameter", f"Check iters / Zernike terms: {exc}")
            return
        if not terms:
            messagebox.showinfo("No terms", "Enter at least one Zernike (n,m) term.")
            return

        slm = self._calibration_slm()
        # Base pattern to correct on top of = the current composed layers.
        try:
            globals_ = self._globals()
            base = compose_phase(self._shape(), self.layers, globals_)
        except (ValueError, ZeroDivisionError) as exc:
            messagebox.showerror("Could not build base pattern", str(exc))
            return

        metric = lambda: feedback.sharpness(self.camera.grab())
        slm.display_phase(base, settle_s=0.0)
        before = metric()

        def on_step(i, x, j):
            self.camera_status_var.set(f"Self-calibrating... step {i + 1}/{n_iter}  sharpness={j:.4g}")
            self.master.update()

        try:
            correction, _hist = autocalibrate.optimize_zernike(
                slm, metric, terms, base_phase=base, radius_px=min(self._shape()) / 2.0,
                n_iter=n_iter, gain=3.0, sigma=0.5, seed=1, settle_s=0.0)
        except Exception as exc:
            messagebox.showerror("Self-calibration failed", str(exc))
            return

        slm.display_phase(base, patterns.zernike_phase(self._shape(), correction,
                                                        radius_px=min(self._shape()) / 2.0), settle_s=0.0)
        after = metric()
        self._show_camera_frame(self.camera.grab())

        # Add the found correction as Zernike layers so it persists in the
        # composed output and is visible/editable in the layer list.
        added = 0
        radius_px = min(self._shape()) / 2.0
        for (n, m), c in correction.items():
            if abs(c) < 0.05:
                continue
            self.layers.append({
                "type": "Zernike Term",
                "params": {"n": n, "m": m, "weight_rad": float(c), "radius_px": radius_px},
                "weight": 1.0, "enabled": True, "center_x": 0.0, "center_y": 0.0,
            })
            added += 1
        self._refresh_listbox()
        self._generate_preview()
        self.camera_status_var.set(
            f"Self-calibration done: sharpness {before:.4g} -> {after:.4g} ({after/before:.1f}x). "
            f"Added {added} Zernike correction layer(s).")

    def _calibration_slm(self):
        """A minimal SLM-like adapter over this GUI so autocalibrate can drive
        it: display_phase renders the pattern (with the current calibration),
        updates an open projector if any, and stores _last_phase for the
        camera feedback. Reuses the GUI's shape/calibration/projector."""
        return _GuiCalibrationSlm(self)

    def _on_close(self):
        if self.camera is not None:
            try:
                self.camera.close()
            except Exception:
                pass
        if self.projector is not None:
            self.projector.close()
        self.master.destroy()


class _GuiCalibrationSlm:
    """Minimal SLM-like adapter over the GUI so `autocalibrate` can drive it.
    Shares `_last_phase` on the app (so a SimFeedbackCamera created from any
    adapter instance reads the phase the loop is currently displaying), renders
    + updates an open projector only when one exists (so a real camera sees the
    SLM change; skipped for the simulated camera, which reads `_last_phase`
    directly -- keeping the loop fast), and pumps the Tk event loop each step so
    the window stays responsive."""

    def __init__(self, app):
        self.app = app

    @property
    def shape(self):
        return self.app._shape()

    @property
    def _last_phase(self):
        return self.app._last_phase

    def display_phase(self, *phases, weights=None, settle_s=0.0):
        total = compose.sum_phases(*phases) if phases else np.zeros(self.shape, dtype=np.float64)
        wrapped = compose.wrap_phase(total)
        self.app._last_phase = wrapped
        if self.app.projector is not None:
            wavelength_nm = float(self.app.g_wavelength_nm.get())
            bit_depth = int(self.app.g_bit_depth.get())
            curve, _ = self.app.cal_library.resolve(wavelength_nm, bit_depth=bit_depth)
            gray = render.phase_to_gray(wrapped, bit_depth=bit_depth, gamma_lut=curve.to_gamma_lut())
            self.app.last_gray = gray
            try:
                self.app.projector.update_image(gray)
            except Exception:
                pass
        try:
            self.app.master.update()
        except tk.TclError:
            pass


def main():
    root = tk.Tk()
    root.minsize(1000, 650)

    # Open the control window on the operator's monitor, never on the SLM's
    # monitor (an HDMI-connected SLM shows up as an ordinary secondary
    # display, and Tk's default window placement doesn't know to avoid it).
    monitors = display.list_monitors()
    slm_monitor = display.default_slm_monitor(monitors)
    control_monitor = next((m for m in monitors if m is not slm_monitor), slm_monitor)
    if control_monitor is not None:
        root.geometry(f"+{control_monitor['x'] + 80}+{control_monitor['y'] + 80}")

    PhaseGeneratorApp(root)
    root.update_idletasks()
    root.mainloop()


if __name__ == "__main__":
    main()
