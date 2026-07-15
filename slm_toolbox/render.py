"""Convert a wrapped phase array (radians, [0, 2*pi)) into the grayscale frame
an SLM actually displays, and save it to disk.

A real SLM's phase response vs. gray level is nonlinear, so `phase_to_gray`
accepts an optional `gamma_lut` (a 1D array of gray-level values indexed by
normalized phase 0..1) built from a per-device calibration measurement. With
no LUT, phase maps linearly onto the full gray range — fine for prototyping,
not for a calibrated device.
"""

import numpy as np
from PIL import Image


def phase_to_gray(phase_wrapped, bit_depth=8, gamma_lut=None):
    """phase_wrapped: array in [0, 2*pi). Returns a uint8 (bit_depth<=8) or
    uint16 (bit_depth>8) array of gray levels."""
    max_val = 2 ** bit_depth - 1
    normalized = phase_wrapped / (2 * np.pi)

    if gamma_lut is not None:
        lut = np.asarray(gamma_lut)
        indices = np.clip(np.round(normalized * (len(lut) - 1)).astype(np.int64), 0, len(lut) - 1)
        gray = lut[indices]
    else:
        gray = np.round(normalized * max_val)

    dtype = np.uint8 if bit_depth <= 8 else np.uint16
    return np.clip(gray, 0, max_val).astype(dtype)


def save_pattern(path, gray_array):
    """Save a rendered gray-level array as an image file (mode inferred from
    dtype: 8-bit -> 'L', 16-bit -> 'I;16')."""
    mode = "L" if gray_array.dtype == np.uint8 else "I;16"
    Image.fromarray(gray_array, mode=mode).save(path)
