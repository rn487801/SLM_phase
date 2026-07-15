"""slm_toolbox — Python phase-pattern generator for spatial light modulator control.

Core building blocks, mirroring the phase-catalog / additive-overlay architecture
surveyed from vendor SLM toolboxes (see ../CLAUDE.md and the project memory):

    grid      — pixel and physical coordinate grids
    patterns  — individual phase generators (vortex, grating, lens, axicon,
                LG mode, Zernike, checkerboard, random)
    compose   — sum phase overlays and wrap to [0, 2*pi)
    render    — convert wrapped phase to an SLM grayscale frame (with optional
                calibration LUT) and save it to disk

Typical usage — a forked vortex hologram (vortex + blazed grating, matching the
existing Mathematica `grating L=<n>_.jpg` outputs):

    from slm_toolbox import patterns, compose, render

    shape = (512, 512)
    phase = compose.sum_phases(
        patterns.vortex_phase(shape, l=3),
        patterns.blazed_grating_phase(shape, period_px=12),
    )
    gray = render.phase_to_gray(compose.wrap_phase(phase))
    render.save_pattern("fork_l3.png", gray)
"""

from . import (grid, patterns, compose, render, display, calibration, calibration_patterns,
               api, simulate, feedback, autocalibrate, notebook)
from .api import SLM
from .notebook import show, to_image, far_field_image

__version__ = "0.2.0"

__all__ = ["grid", "patterns", "compose", "render", "display", "calibration", "calibration_patterns",
           "api", "SLM", "simulate", "feedback", "autocalibrate", "notebook",
           "show", "to_image", "far_field_image", "__version__"]
