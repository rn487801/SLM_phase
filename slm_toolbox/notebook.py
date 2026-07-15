"""Jupyter/IPython convenience: turn phase or gray-level arrays into inline
images. A Jupyter cell auto-displays a returned PIL.Image, so

    from slm_toolbox import patterns, show
    show(patterns.vortex_phase((512, 512), l=3))

renders the hologram inline. PIL-only (already a core dependency) -- no
matplotlib needed for basic display.
"""

import numpy as np
from PIL import Image

from . import compose


def to_image(arr, kind="auto", max_size=None):
    """Convert an array to a grayscale PIL.Image for inline display.

    kind: "phase" wraps to [0, 2*pi) and maps to 0..255 (for an unwrapped
    phase array in radians); "gray" treats the array as a gray-level frame
    (uint8/uint16) or normalizes a float intensity map to 0..255; "auto"
    picks "gray" for uint8/uint16 arrays and "phase" for float arrays.
    max_size (px) optionally thumbnails the result for a compact preview."""
    arr = np.asarray(arr)
    if kind == "auto":
        kind = "gray" if arr.dtype in (np.uint8, np.uint16) else "phase"

    if kind == "phase":
        wrapped = compose.wrap_phase(arr.astype(np.float64))
        data = (wrapped / (2 * np.pi) * 255).astype(np.uint8)
    else:
        if arr.dtype == np.uint8:
            data = arr
        elif arr.dtype == np.uint16:
            data = (arr >> 8).astype(np.uint8)
        else:
            a = arr.astype(np.float64)
            lo, hi = float(a.min()), float(a.max())
            data = (((a - lo) / (hi - lo)) * 255).astype(np.uint8) if hi > lo else np.zeros(a.shape, np.uint8)

    img = Image.fromarray(data, mode="L")
    if max_size:
        img = img.copy()
        img.thumbnail((max_size, max_size))
    return img


def show(arr, kind="auto", max_size=512):
    """to_image(...) with a default preview size -- return it as the last
    expression in a notebook cell to display it inline."""
    return to_image(arr, kind=kind, max_size=max_size)


def far_field_image(phase_rad, wavelength_m, pixel_pitch_m, waist_m=None, gamma=0.4, max_size=512):
    """Simulate and return the predicted far-field (focal-plane) beam image
    for a phase pattern -- so you can preview the actual beam shape (doughnut,
    ring, spot) inline, no hardware. gamma < 1 compresses the large dynamic
    range for display."""
    from . import simulate  # local: avoids importing simulate unless used
    amplitude = None
    if waist_m is not None:
        amplitude = simulate.gaussian_illumination(np.asarray(phase_rad).shape, waist_m, pixel_pitch_m)
    intensity, _ = simulate.simulate_far_field(phase_rad, wavelength_m, pixel_pitch_m, amplitude=amplitude)
    disp = np.clip(intensity, 0, 1) ** gamma
    return to_image(disp, kind="gray", max_size=max_size)
