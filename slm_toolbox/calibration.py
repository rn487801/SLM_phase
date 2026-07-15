"""Wavelength-dependent gray-level -> phase calibration.

Why this exists: a phase-only LC-SLM doesn't actually take a "phase" as
input — the host sends an 8-bit (or 16-bit) gray level per pixel, and the
SLM's own driver electronics convert that to a voltage, which sets the
liquid crystal's birefringence and therefore the phase retardation. That
voltage->phase relationship is nonlinear AND wavelength-dependent (for a
fixed voltage, phase retardation scales roughly as 1/wavelength -- see
`rescale_to_wavelength`), so "gray level 255 = 2*pi phase" is only true at
one specific wavelength the panel happened to be calibrated at. This module
represents a measured gray->phase curve (per wavelength) and inverts it into
the `gamma_lut` that `render.phase_to_gray` already accepts, so a single
control parameter (the Wavelength field in the GUI) picks the right
calibration automatically.

This module does NOT invent calibration numbers -- there is no built-in
"default" curve, because a wrong fabricated LUT would silently corrupt every
pattern sent to real hardware. See calibration_SOP.md for how to measure a
real curve for your panel; `CalibrationCurve.linear_fallback` is the explicit,
clearly-labeled placeholder used until a real measurement is loaded.
"""

import glob
import json
import os

import numpy as np


def efficiency_to_phase_diff(efficiency, efficiency_at_pi):
    """Invert the two-level-grating 1st-order diffraction efficiency relation
    eta = eta_max * sin^2(dphi/2) for the PRINCIPAL branch dphi in [0, pi]
    (see calibration_SOP.md Method C). `efficiency_at_pi` is the measured
    efficiency at the sweep's peak (believed to be dphi=pi); efficiency can
    be in any consistent unit (raw power-meter reading, camera counts, etc.)
    since only the ratio to the peak matters."""
    ratio = np.clip(np.asarray(efficiency, dtype=np.float64) / efficiency_at_pi, 0, 1)
    return 2 * np.arcsin(np.sqrt(ratio))


def unwrap_efficiency_sweep(gray_levels, efficiencies):
    """Given a gray-level sweep and its measured 1st-order diffraction
    efficiency at each point (Method C), recover the unwrapped phase
    DIFFERENCE curve vs. gray level.

    sin^2(dphi/2) is not invertible on its own -- it's zero at both dphi=0
    and dphi=2*pi and only unambiguous on the way up to its peak at dphi=pi.
    This assumes what the calibration itself assumes (a well-behaved panel):
    phase increases monotonically with gray level across the sweep. Under
    that assumption, the efficiency curve's single interior peak marks
    dphi=pi; before it, the principal arcsin branch is valid; after it,
    phase keeps increasing while efficiency mirrors back down, so the branch
    flips (dphi = 2*pi - principal). Needs a sweep that actually reaches a
    peak (i.e. actually spans through dphi=pi) to work.

    Two inherent (not fixable in software) accuracy limits of this method,
    confirmed against synthetic ground-truth data: (1) since eta_max is taken
    from whichever *discrete sample* happens to be the sweep's max, accuracy
    right around dphi=pi improves with denser sampling there (the true
    continuous peak rarely lands exactly on a sample); (2) near dphi=0 and
    dphi=2*pi, sin^2 is flat, so arcsin(sqrt(.))'s derivative diverges and
    small measurement noise causes disproportionately large phase error --
    average multiple readings near the sweep's endpoints if precision there
    matters.

    Returns (gray_levels_sorted, phase_diff_rad)."""
    gray_levels = np.asarray(gray_levels, dtype=np.float64)
    efficiencies = np.asarray(efficiencies, dtype=np.float64)
    if gray_levels.shape != efficiencies.shape or gray_levels.size < 3:
        raise ValueError("Need matching gray_levels/efficiencies arrays with at least 3 points")

    order = np.argsort(gray_levels)
    gray_levels = gray_levels[order]
    efficiencies = efficiencies[order]

    peak_idx = int(np.argmax(efficiencies))
    eta_max = efficiencies[peak_idx]
    if eta_max <= 0:
        raise ValueError("Peak efficiency must be > 0 -- check the measurements.")
    if peak_idx == 0 or peak_idx == len(efficiencies) - 1:
        raise ValueError(
            "Efficiency peak is at the first or last sample -- the sweep doesn't appear to reach "
            "dphi=pi (a full swing). Extend the gray-level range so the efficiency clearly rises "
            "then falls."
        )

    phase = np.empty_like(efficiencies)
    principal = efficiency_to_phase_diff(efficiencies, eta_max)
    phase[:peak_idx + 1] = principal[:peak_idx + 1]
    phase[peak_idx + 1:] = 2 * np.pi - principal[peak_idx + 1:]
    return gray_levels, phase


class CalibrationCurve:
    """A measured (or approximated) gray-level -> phase curve for one
    wavelength. `gray` and `phase_rad` are parallel arrays; phase must be
    monotonically non-decreasing in gray (a well-behaved panel over its
    usable 0..2*pi range) covering a total span of >= 2*pi somewhere in the
    calibrated gray range."""

    def __init__(self, wavelength_nm, gray, phase_rad, bit_depth=8, source="measured", notes=""):
        gray = np.asarray(gray, dtype=np.float64)
        phase_rad = np.asarray(phase_rad, dtype=np.float64)
        if gray.shape != phase_rad.shape or gray.size < 2:
            raise ValueError("gray and phase_rad must be equal-length arrays with at least 2 points")
        order = np.argsort(gray)
        self.wavelength_nm = wavelength_nm
        self.gray = gray[order]
        self.phase_rad = phase_rad[order]
        self.bit_depth = bit_depth
        self.source = source
        self.notes = notes

    @classmethod
    def linear_fallback(cls, wavelength_nm, bit_depth=8):
        """Uncalibrated placeholder: assumes gray 0..max maps linearly onto
        phase 0..2*pi. Physically wrong on real hardware -- only use until a
        real curve is measured (see calibration_SOP.md)."""
        max_gray = 2 ** bit_depth - 1
        return cls(wavelength_nm, [0, max_gray], [0.0, 2 * np.pi], bit_depth=bit_depth,
                   source="uncalibrated-linear", notes="No measurement on file; linear 0..2*pi placeholder.")

    def rescale_to_wavelength(self, new_wavelength_nm):
        """Approximate this curve at a different wavelength via
        Delta_phi(V, lambda) ~ Delta_phi(V, lambda_ref) * lambda_ref / lambda
        (phase retardation for a fixed liquid-crystal birefringence scales
        inversely with wavelength). This is a physics-based estimate, not a
        real measurement -- accurate enough to get close, but re-measuring
        at the actual wavelength (calibration_SOP.md) is what removes
        residual error from wavelength-dependent birefringence dispersion."""
        scale = self.wavelength_nm / new_wavelength_nm
        return CalibrationCurve(
            new_wavelength_nm, self.gray, self.phase_rad * scale, bit_depth=self.bit_depth,
            source=f"rescaled-from-{self.wavelength_nm}nm",
            notes=f"Approximated from a {self.wavelength_nm}nm measurement via 1/wavelength scaling; not directly measured.",
        )

    def to_gamma_lut(self, n=None):
        """Invert the curve into the gamma_lut array render.phase_to_gray
        expects: gamma_lut[i] is the gray level that produces phase
        2*pi*i/(n-1), for i in 0..n-1."""
        n = n or (2 ** self.bit_depth)
        target_phase = np.linspace(0, 2 * np.pi, n)
        max_gray = 2 ** self.bit_depth - 1
        # Real measured curves often saturate (flat/non-increasing phase) near
        # gray=0 and gray=max as the liquid crystal hits its extremes; nudge
        # any non-increasing points so np.interp's inversion is well-defined
        # instead of picking an arbitrary point within the flat region.
        phase_strict = self.phase_rad.copy()
        for i in range(1, len(phase_strict)):
            if phase_strict[i] <= phase_strict[i - 1]:
                phase_strict[i] = phase_strict[i - 1] + 1e-9
        gray = np.interp(target_phase, phase_strict, self.gray, left=self.gray[0], right=self.gray[-1])
        return np.clip(np.round(gray), 0, max_gray).astype(np.uint8 if self.bit_depth <= 8 else np.uint16)

    def to_dict(self):
        return {
            "wavelength_nm": self.wavelength_nm,
            "bit_depth": self.bit_depth,
            "gray": self.gray.tolist(),
            "phase_rad": self.phase_rad.tolist(),
            "source": self.source,
            "notes": self.notes,
        }

    @classmethod
    def from_efficiency_sweep(cls, wavelength_nm, gray_levels, efficiencies, gray_ref=0, bit_depth=8, notes=""):
        """Build a curve from Method C of calibration_SOP.md: a two-level
        grating's 1st-order diffraction efficiency vs. the test gray level,
        measured against a fixed reference gray level (gray_ref, phase
        defined as 0 there). See `unwrap_efficiency_sweep` for the inversion
        this wraps."""
        gray, phase = unwrap_efficiency_sweep(gray_levels, efficiencies)
        return cls(wavelength_nm, gray, phase, bit_depth=bit_depth, source="measured-diffraction-efficiency",
                   notes=notes or f"From a two-level grating efficiency sweep against gray_ref={gray_ref}.")

    @classmethod
    def from_dict(cls, d):
        return cls(d["wavelength_nm"], d["gray"], d["phase_rad"],
                   bit_depth=d.get("bit_depth", 8), source=d.get("source", "measured"),
                   notes=d.get("notes", ""))

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))


class CalibrationLibrary:
    """A folder of saved per-wavelength CalibrationCurve JSON files. Resolves
    a requested wavelength to the best available curve: an exact (within
    tolerance) measured match, else the nearest measured curve rescaled to
    the requested wavelength (approximate), else an uncalibrated linear
    fallback -- always reports which one it used."""

    def __init__(self, directory):
        self.directory = directory

    def _measured_curves(self):
        curves = []
        if os.path.isdir(self.directory):
            for path in sorted(glob.glob(os.path.join(self.directory, "*.json"))):
                try:
                    curves.append(CalibrationCurve.load(path))
                except (OSError, ValueError, KeyError):
                    continue
        return curves

    def resolve(self, wavelength_nm, bit_depth=8, tolerance_nm=2.0):
        """Returns (CalibrationCurve, status_message)."""
        measured = self._measured_curves()
        if not measured:
            return (
                CalibrationCurve.linear_fallback(wavelength_nm, bit_depth),
                f"No calibration files in {self.directory!r} -- using uncalibrated linear 0..2*pi mapping. "
                "See calibration_SOP.md.",
            )

        exact = min(measured, key=lambda c: abs(c.wavelength_nm - wavelength_nm))
        if abs(exact.wavelength_nm - wavelength_nm) <= tolerance_nm:
            return exact, f"Using measured calibration for {exact.wavelength_nm}nm."

        rescaled = exact.rescale_to_wavelength(wavelength_nm)
        return (
            rescaled,
            f"No measurement at {wavelength_nm}nm -- approximating from the {exact.wavelength_nm}nm "
            "measurement via 1/wavelength scaling. Re-calibrate at this wavelength for best accuracy.",
        )

    def save(self, curve):
        filename = f"{curve.wavelength_nm:g}nm.json"
        curve.save(os.path.join(self.directory, filename))
