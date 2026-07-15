"""Programmatic SLM control for automated optoelectronic measurement scripts.

Everything else in slm_toolbox (patterns/compose/render/calibration/display)
is a library of pieces; this module wires them into one synchronous object,
`SLM`, meant to be imported directly into a measurement script -- no GUI, no
button clicks, no mainloop() call required from the caller. A hidden Tk root
is managed internally purely because the display mechanism (an HDMI-
connected SLM acting as a secondary monitor) is a Tkinter window under the
hood; nothing about the API itself is GUI-shaped.

Typical usage -- sweep a vortex charge and read a power meter at each step:

    from slm_toolbox.api import SLM

    with SLM(wavelength_nm=1064) as slm:
        for l in range(-3, 4):
            slm.display_phase(slm.vortex(l), slm.grating(period_px=12))
            power_mw = my_power_meter.read()
            log(l, power_mw)

Or run a fully automated Method C calibration (calibration_SOP.md) against
your own instrument's read function:

    with SLM(wavelength_nm=1064) as slm:
        curve = slm.run_efficiency_calibration(measure_fn=my_power_meter.read)
"""

import os
import time
import tkinter as tk

import numpy as np

from . import patterns, compose, render, display, calibration, calibration_patterns

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CALIBRATIONS_DIR = os.path.join(os.path.dirname(PACKAGE_DIR), "calibrations")

list_monitors = display.list_monitors  # re-exported for discovery, e.g. SLM(monitor_index=...)


class SLM:
    """A phase-only SLM connected via HDMI, controlled programmatically.

    Picks the first non-primary monitor by default (the common case: your
    operator display is primary, the SLM is the secondary HDMI output).
    Pass `monitor_index` (see `slm_toolbox.api.list_monitors()`) to target a
    specific one explicitly.
    """

    def __init__(self, monitor_index=None, wavelength_nm=1064.0, pixel_pitch_m=8e-6,
                 waist_m=40e-6, bit_depth=8, calibration_dir=None):
        monitors = display.list_monitors()
        if not monitors:
            raise RuntimeError("No monitors detected.")
        if monitor_index is None:
            monitor = display.default_slm_monitor(monitors)
        else:
            if not (0 <= monitor_index < len(monitors)):
                raise ValueError(f"monitor_index {monitor_index} out of range (0..{len(monitors) - 1})")
            monitor = monitors[monitor_index]

        self.monitor = monitor
        self.shape = (monitor["height"], monitor["width"])
        self.wavelength_nm = wavelength_nm
        self.pixel_pitch_m = pixel_pitch_m
        self.waist_m = waist_m
        self.bit_depth = bit_depth

        self._cal_library = calibration.CalibrationLibrary(calibration_dir or DEFAULT_CALIBRATIONS_DIR)
        self._root = tk.Tk()
        self._root.withdraw()
        self._projector = None
        self._last_gray = None
        self._last_phase = None   # wrapped phase (radians) last rendered; used by feedback loops
        self._last_calibration_status = None

    # ---------- physical-parameter helpers ----------
    def _optics(self):
        return {
            "wavelength_m": self.wavelength_nm * 1e-9,
            "pixel_pitch_m": self.pixel_pitch_m,
            "waist_m": self.waist_m,
        }

    def calibration_status(self):
        """Returns the human-readable status of whichever calibration curve
        would currently be applied (exact / rescaled-approximate /
        uncalibrated-linear-fallback) for self.wavelength_nm -- log this
        alongside measurement data so you know what corrected the output."""
        _curve, msg = self._cal_library.resolve(self.wavelength_nm, bit_depth=self.bit_depth)
        return msg

    # ---------- phase pattern generators (shape/optics pre-bound) ----------
    def vortex(self, l, center=None):
        return patterns.vortex_phase(self.shape, l=l, center=center)

    def grating(self, period_px, angle_deg=0.0, center=None):
        return patterns.blazed_grating_phase(self.shape, period_px, angle_deg, center=center)

    def lens(self, focal_length_m, converging=True, center=None):
        return patterns.fresnel_lens_phase(self.shape, focal_length_m, self.wavelength_nm * 1e-9,
                                            self.pixel_pitch_m, center=center, converging=converging)

    def steer_to(self, dx_m, dy_m, focal_length_m, center=None):
        """Beam steering / light-path tilt: a linear phase ramp that moves a
        lens's focused spot to a transverse position (dx_m, dy_m) from the
        optical axis at that lens's focal plane. Pair with
        `slm.lens(focal_length_m)` (same focal_length_m) in the same
        display_phase(...) call to actually focus there."""
        return patterns.beam_position_phase(self.shape, dx_m, dy_m, focal_length_m,
                                             self.wavelength_nm * 1e-9, self.pixel_pitch_m, center=center)

    def axicon(self, cone_angle_rad, sign=1.0, center=None):
        return patterns.axicon_phase(self.shape, cone_angle_rad, self.wavelength_nm * 1e-9,
                                      self.pixel_pitch_m, center=center, sign=sign)

    def lg_mode_field(self, p, l, z_m=0.0, center=None):
        """Returns the complex LG_p,l field; use np.angle(...) for phase-only."""
        return patterns.lg_mode_field(self.shape, p, l, self.waist_m, self.wavelength_nm * 1e-9,
                                       self.pixel_pitch_m, z_m=z_m, center=center)

    def zernike(self, coeffs, radius_px, center=None):
        return patterns.zernike_phase(self.shape, coeffs, radius_px, center=center)

    def checkerboard(self, period_px, low=0.0, high=np.pi, center=None):
        return patterns.checkerboard_phase(self.shape, period_px, low=low, high=high, center=center)

    def random_phase(self, seed=None):
        return patterns.random_phase(self.shape, seed=seed)

    # ---------- render + display ----------
    def render(self, *phases, weights=None):
        """Sum any number of phase arrays (radians, e.g. from .vortex()/.lens()/
        etc, optionally weighted), wrap, and apply the current wavelength's
        calibration -- returns the gray-level frame without displaying it."""
        if weights is not None:
            phases = [p * w for p, w in zip(phases, weights)]
        total = compose.sum_phases(*phases) if phases else np.zeros(self.shape, dtype=np.float64)
        wrapped = compose.wrap_phase(total)
        self._last_phase = wrapped
        curve, status = self._cal_library.resolve(self.wavelength_nm, bit_depth=self.bit_depth)
        self._last_calibration_status = status
        gray = render.phase_to_gray(wrapped, bit_depth=self.bit_depth, gamma_lut=curve.to_gamma_lut())
        self._last_gray = gray
        return gray

    def display_phase(self, *phases, weights=None, settle_s=0.05):
        """render(*phases, weights=weights) then show it on the SLM. Blocks
        for settle_s (pumping the Tk event loop throughout, so it's safe in
        a tight measurement loop) to give the liquid crystal time to settle
        before you take a reading -- tune settle_s to your panel."""
        gray = self.render(*phases, weights=weights)
        self._show_gray(gray, settle_s=settle_s)
        return gray

    def display_gray(self, gray_array, settle_s=0.05):
        """Show a raw gray-level array directly, bypassing the phase pipeline
        -- e.g. for calibration_patterns test patterns."""
        self._last_gray = np.asarray(gray_array)
        self._show_gray(self._last_gray, settle_s=settle_s)

    def blank(self, settle_s=0.05):
        """Display a uniform gray=0 frame (no modulation)."""
        self.display_gray(np.zeros(self.shape, dtype=np.uint8), settle_s=settle_s)

    def _show_gray(self, gray_array, settle_s):
        if self._projector is None:
            self._projector = display.ProjectorWindow(self._root, self.monitor, gray_array,
                                                        on_close=self._on_projector_closed)
        else:
            self._projector.update_image(gray_array)
        self._pump_events(settle_s)

    def _on_projector_closed(self):
        self._projector = None

    def _pump_events(self, duration_s):
        deadline = time.monotonic() + max(duration_s, 0.01)
        while time.monotonic() < deadline:
            self._root.update()
            time.sleep(0.005)

    # ---------- calibration ----------
    def run_efficiency_calibration(self, measure_fn, gray_levels=None, gray_ref=0, grating_period_px=20,
                                    settle_s=0.1, save=True):
        """Fully automated Method C calibration (calibration_SOP.md): for
        each gray level, projects the reference-vs-test grating and calls
        `measure_fn()` -- your own instrument read, e.g. a power meter or DAQ
        channel returning a scalar 1st-order-diffraction-efficiency-proxy
        reading (any consistent unit; only relative values matter). Needs
        the readings to visibly rise then fall across the sweep (i.e. the
        sweep must actually pass through a phase difference of pi) to invert
        correctly -- see calibration.unwrap_efficiency_sweep.

        Returns the resulting CalibrationCurve (already saved for
        self.wavelength_nm unless save=False)."""
        if gray_levels is None:
            max_gray = 2 ** self.bit_depth - 1
            gray_levels = calibration_patterns.default_efficiency_sweep_levels(gray_ref, max_gray)

        efficiencies = []
        for g in gray_levels:
            pattern = calibration_patterns.two_level_grating_pattern(
                self.shape, grating_period_px, gray_ref, g)
            self.display_gray(pattern, settle_s=settle_s)
            efficiencies.append(measure_fn())

        curve = calibration.CalibrationCurve.from_efficiency_sweep(
            self.wavelength_nm, gray_levels, efficiencies, gray_ref=gray_ref, bit_depth=self.bit_depth,
            notes=f"Automated via SLM.run_efficiency_calibration, grating_period_px={grating_period_px}.",
        )
        if save:
            self._cal_library.save(curve)
        return curve

    def project_self_referenced_pattern(self, piston_gray, grating_gray_a=0, grating_gray_b=255,
                                         grating_period_px=15, split_fraction=0.5,
                                         orientation="horizontal", settle_s=0.05):
        """Display the Method A base pattern (calibration_SOP.md) for a given
        piston gray level -- phase extraction from the resulting fringes is
        yours to do (camera + your own fringe analysis); once you have
        gray->phase points, build a curve with
        `calibration.CalibrationCurve(wavelength_nm, gray, phase_rad)` and
        `.save(...)` (or the CalibrationLibrary via
        `slm._cal_library.save(curve)`)."""
        pattern = calibration_patterns.self_referenced_calibration_pattern(
            self.shape, piston_gray, grating_gray_a, grating_gray_b, grating_period_px,
            split_fraction=split_fraction, orientation=orientation)
        self.display_gray(pattern, settle_s=settle_s)
        return pattern

    # ---------- lifecycle ----------
    def close(self):
        if self._projector is not None:
            self._projector.close()
        self._root.destroy()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self):
        return (f"SLM(shape={self.shape[1]}x{self.shape[0]}, wavelength_nm={self.wavelength_nm}, "
                f"monitor=({self.monitor['x']},{self.monitor['y']}))")
