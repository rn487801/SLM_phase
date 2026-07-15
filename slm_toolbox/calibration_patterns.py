"""Raw gray-level test patterns for measuring a calibration curve
(calibration_SOP.md). These bypass the normal phase -> gamma_lut -> gray
pipeline entirely: during calibration, gray level is the *independent
variable* you're sweeping and measuring against, not something derived from
a target phase (you don't have a calibration curve yet -- that's the whole
point). Every function here returns a raw gray-level array ready for
`display.ProjectorWindow` or `render.save_pattern` directly.
"""

import numpy as np

from .grid import pixel_grid


def two_level_grating_pattern(shape, period_px, gray_a, gray_b, angle_deg=0.0, duty=0.5, center=None):
    """Binary (Ronchi) grating alternating between two fixed gray levels --
    the calibration_SOP.md Method C base pattern. Its 1st-order diffraction
    efficiency depends only on the phase DIFFERENCE the panel produces
    between gray_a and gray_b (see calibration.unwrap_efficiency_sweep), so
    holding gray_a fixed as a reference and sweeping gray_b traces out the
    phase-difference-vs-gray curve."""
    x, y = pixel_grid(shape, center)
    theta = np.deg2rad(angle_deg)
    proj = x * np.cos(theta) + y * np.sin(theta)
    frac = np.mod(proj / period_px, 1.0)
    max_gray = max(gray_a, gray_b)
    dtype = np.uint8 if max_gray <= 255 else np.uint16
    return np.where(frac < duty, gray_a, gray_b).astype(dtype)


def self_referenced_calibration_pattern(shape, piston_gray, grating_gray_a, grating_gray_b,
                                          grating_period_px, split_fraction=0.5, orientation="horizontal"):
    """calibration_SOP.md Method A base pattern: one region of the SLM shows
    a two-level grating (diffracts into a tilted plane wave), the other a
    uniform 'piston' gray level (the value under test, undiffracted
    reference wave) -- the two interfere downstream with no external
    interferometer optics needed, just a collimated beam and a camera."""
    h, w = shape
    grating = two_level_grating_pattern(shape, grating_period_px, grating_gray_a, grating_gray_b)
    pattern = grating.copy()
    if orientation == "horizontal":
        split = int(w * split_fraction)
        pattern[:, split:] = piston_gray
    elif orientation == "vertical":
        split = int(h * split_fraction)
        pattern[split:, :] = piston_gray
    else:
        raise ValueError(f"orientation must be 'horizontal' or 'vertical', got {orientation!r}")
    return pattern


def default_efficiency_sweep_levels(gray_ref=0, max_gray=255, n=17):
    """A sensible default set of test gray levels for Method C: evenly
    spaced from gray_ref to max_gray, always including both endpoints."""
    return sorted(set(int(round(g)) for g in np.linspace(gray_ref, max_gray, n)))
