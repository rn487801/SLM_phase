"""Coordinate grids shared by every phase generator.

Two flavors: pixel-normalized (grating/vortex/checkerboard need no physical
units) and physical, in meters (lens/axicon/LG modes need real units to relate
focal length / wavelength / cone angle to the pattern).
"""

import numpy as np


def pixel_grid(shape, center=None):
    """Return (x, y) integer-valued float arrays, centered on `center` (defaults
    to the array's geometric center), in pixel units."""
    h, w = shape
    if center is None:
        cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    else:
        cx, cy = center
    y, x = np.indices((h, w), dtype=np.float64)
    return x - cx, y - cy


def polar_grid(shape, center=None):
    """Return (rho, phi) in pixel units; phi in radians via atan2(y, x)."""
    x, y = pixel_grid(shape, center)
    rho = np.hypot(x, y)
    phi = np.arctan2(y, x)
    return rho, phi


def physical_grid(shape, pixel_pitch_m, center=None):
    """Return (x, y) in meters, given the SLM's physical pixel pitch."""
    x, y = pixel_grid(shape, center)
    return x * pixel_pitch_m, y * pixel_pitch_m
