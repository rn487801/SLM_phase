"""Predict what a phase pattern will actually produce optically -- Fraunhofer
(far-field / focal-plane-of-a-lens) diffraction via FFT.

Useful two ways: (1) a genuine preview of the beam shape a hologram will
produce (doughnut for a vortex, ring/Bessel-like for an axicon, split orders
for a checkerboard, ...) before ever touching hardware; (2) physics-based
correctness tests that don't need real hardware at all -- e.g. a pure vortex
phase MUST diffract to zero intensity exactly on-axis (the phase
singularity), which is a hard physical fact independent of any calibration
or display, and a good regression check for the pattern generators.
"""

import numpy as np

from .grid import physical_grid


def gaussian_illumination(shape, waist_m, pixel_pitch_m, center=None):
    """Real amplitude envelope for a Gaussian-beam illumination of the SLM
    (as opposed to the default uniform/plane-wave illumination) -- pass as
    `amplitude` to simulate_far_field for a more realistic prediction."""
    x, y = physical_grid(shape, pixel_pitch_m, center)
    rho2 = x ** 2 + y ** 2
    return np.exp(-rho2 / waist_m ** 2)


def simulate_far_field(phase_rad, wavelength_m, pixel_pitch_m, amplitude=None, pad_factor=4):
    """Fraunhofer far-field (equivalently: the focal-plane pattern behind an
    ideal lens) of a phase-only mask, via FFT.

    amplitude: optional real illumination envelope (e.g. gaussian_illumination);
    defaults to uniform illumination (amplitude=1 everywhere).
    pad_factor: zero-pads the field by this factor before the FFT for finer
    angular sampling in the result (>=2; higher = smoother far field, more
    compute). The padded field is centered, so the SLM's actual aperture
    stays physically centered in the (larger) simulation grid.

    Returns (intensity, angular_pixel_rad): intensity is normalized to a
    peak of 1; angular_pixel_rad is the angular extent (radians) of one
    far-field pixel, from the standard FFT-diffraction relation
    d_theta = wavelength / (N_padded * pixel_pitch) -- multiply by a lens
    focal length to get physical position on a camera/screen at that focus.
    """
    phase_rad = np.asarray(phase_rad, dtype=np.float64)
    h, w = phase_rad.shape
    if amplitude is None:
        amplitude = np.ones_like(phase_rad)
    field = amplitude * np.exp(1j * phase_rad)

    hp, wp = h * pad_factor, w * pad_factor
    padded = np.zeros((hp, wp), dtype=np.complex128)
    y0, x0 = (hp - h) // 2, (wp - w) // 2
    padded[y0:y0 + h, x0:x0 + w] = field

    far_field = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(padded)))
    intensity = np.abs(far_field) ** 2
    peak = intensity.max()
    if peak > 0:
        intensity = intensity / peak

    angular_pixel_rad = wavelength_m / (wp * pixel_pitch_m)
    return intensity, angular_pixel_rad


def on_axis_intensity(intensity):
    """The far field's center-pixel intensity (0..1, already peak-normalized
    by simulate_far_field) -- should be ~0 for a pure vortex (phase
    singularity -> destructive interference on-axis), non-zero for most
    other patterns.

    Caveat confirmed empirically (see tests/test_simulate.py): on a square
    pixel grid, this null is essentially exact (~machine precision) for
    vortex charge l NOT divisible by 4, but leaves a real nonzero residual
    when l % 4 == 0 -- the grid's own 4-fold (C4) rotational symmetry
    coincides with the vortex winding number in that case. This isn't a
    simulator artifact to fix; it reflects genuine aperture-truncation
    physics that applies to any pixelated square/rectangular device,
    including a real SLM's active area, not just this simulation."""
    h, w = intensity.shape
    return float(intensity[h // 2, w // 2])


def radial_profile(intensity, center=None, n_bins=None):
    """Azimuthally-averaged radial intensity profile -- collapses a 2D far
    field into (radius_px, mean_intensity), useful for characterizing ring
    radius/width (OAM doughnuts, axicon Bessel rings) without eyeballing an
    image. n_bins defaults to the array's own resolution along the shorter
    axis."""
    h, w = intensity.shape
    cy, cx = (center if center is not None else (h / 2, w / 2))
    y, x = np.indices((h, w))
    r = np.hypot(x - cx, y - cy)
    n_bins = n_bins or int(min(h, w) / 2)
    r_max = r.max()
    bin_edges = np.linspace(0, r_max, n_bins + 1)
    bin_idx = np.clip(np.digitize(r.ravel(), bin_edges) - 1, 0, n_bins - 1)
    sums = np.bincount(bin_idx, weights=intensity.ravel(), minlength=n_bins)
    counts = np.bincount(bin_idx, minlength=n_bins)
    counts[counts == 0] = 1
    radii = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    return radii, sums / counts
