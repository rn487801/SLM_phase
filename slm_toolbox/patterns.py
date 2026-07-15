"""Individual phase-pattern generators.

Every function returns an *unwrapped* phase array in radians, same shape as the
requested `shape`. Combine several with `compose.sum_phases` then
`compose.wrap_phase` before rendering — additive-overlay composition is the
pattern vendor SLM software (and this project's own Mathematica prototype) both
use, rather than interleaving.
"""

import numpy as np
from scipy.special import eval_genlaguerre
from math import factorial

from .grid import pixel_grid, polar_grid, physical_grid


def vortex_phase(shape, l, center=None):
    """Spiral/vortex phase l*phi — the OAM topological-charge term."""
    _, phi = polar_grid(shape, center)
    return l * phi


def blazed_grating_phase(shape, period_px, angle_deg=0.0, center=None):
    """Linear (blazed) grating phase, period in pixels, oriented at angle_deg
    from the x-axis. Concentrates diffracted power into a single order (unlike
    a binary on/off grating, which splits roughly evenly into +-1 orders)."""
    x, y = pixel_grid(shape, center)
    theta = np.deg2rad(angle_deg)
    x_proj = x * np.cos(theta) + y * np.sin(theta)
    return 2 * np.pi * x_proj / period_px


def beam_position_phase(shape, dx_m, dy_m, focal_length_m, wavelength_m, pixel_pitch_m, center=None):
    """A linear phase ramp (the same physical thing as blazed_grating_phase)
    parameterized by where you want the spot to land instead of by grating
    period/angle: steers a lens's focused spot to a transverse position
    (dx_m, dy_m) from the optical axis at that lens's focal plane. Pair with
    fresnel_lens_phase(focal_length_m=<same value>) to actually focus there —
    on its own this just tilts the propagation direction (beam steering /
    "tilt the light path") by the paraxial angle displacement/focal_length_m.

    Derivation: a linear phase phi(x) = k*theta*x tilts the wavefront by
    angle theta, which a downstream lens of focal length f focuses to a
    transverse offset f*theta. Solving for theta = dx_m/focal_length_m and
    substituting k = 2*pi/wavelength_m gives the phase gradient used here."""
    x, y = pixel_grid(shape, center)
    k = 2 * np.pi / wavelength_m
    return (k / focal_length_m) * (dx_m * x + dy_m * y) * pixel_pitch_m


def fresnel_lens_phase(shape, focal_length_m, wavelength_m, pixel_pitch_m, center=None, converging=True):
    """Quadratic (Fresnel) lens phase — adds or removes focus."""
    x, y = physical_grid(shape, pixel_pitch_m, center)
    rho2 = x ** 2 + y ** 2
    sign = -1.0 if converging else 1.0
    return sign * np.pi * rho2 / (wavelength_m * focal_length_m)


def axicon_phase(shape, cone_angle_rad, wavelength_m, pixel_pitch_m, center=None, sign=1.0):
    """Conical (axicon) phase, linear in rho. sign=+1 -> positive axicon
    (converging cone, produces a Bessel beam); sign=-1 -> negative axicon
    (diverging cone, produces an annular/ring beam)."""
    x, y = physical_grid(shape, pixel_pitch_m, center)
    rho = np.hypot(x, y)
    return sign * (2 * np.pi / wavelength_m) * rho * np.sin(cone_angle_rad)


def lg_mode_field(shape, p, l, w0_m, wavelength_m, pixel_pitch_m, z_m=0.0, center=None):
    """Complex Laguerre-Gaussian LG_{p,l} field amplitude, matching the
    normalization/Gouy-phase convention used in the Mathematica notebook.
    Returns a complex array; use np.angle(...) for phase-only encoding or
    np.abs(...)**2 for the intensity preview."""
    x, y = physical_grid(shape, pixel_pitch_m, center)
    rho = np.hypot(x, y)
    phi = np.arctan2(y, x)

    zR = np.pi * w0_m ** 2 / wavelength_m
    wz = w0_m * np.sqrt(1 + (z_m / zR) ** 2)
    gouy = np.arctan2(z_m, zR)
    k = 2 * np.pi / wavelength_m

    norm = np.sqrt(2 * factorial(p) / (np.pi * factorial(p + abs(l))))
    radial_term = (np.sqrt(2) * rho / wz) ** abs(l)
    laguerre_term = eval_genlaguerre(p, abs(l), 2 * rho ** 2 / wz ** 2)
    envelope = np.exp(-(rho ** 2) / wz ** 2)

    curvature_phase = 0.0
    if z_m != 0:
        curvature_phase = k * z_m * rho ** 2 / (2 * (z_m ** 2 + zR ** 2))

    phase = l * phi - curvature_phase + (2 * p + abs(l) + 1) * gouy
    amplitude = (norm / wz) * radial_term * laguerre_term * envelope
    return amplitude * np.exp(1j * phase)


def _zernike_radial(n, m, rho):
    m = abs(m)
    r = np.zeros_like(rho)
    for k in range((n - m) // 2 + 1):
        c = (-1) ** k * factorial(n - k)
        c /= factorial(k) * factorial((n + m) // 2 - k) * factorial((n - m) // 2 - k)
        r = r + c * rho ** (n - 2 * k)
    return r


def zernike_phase(shape, coeffs, radius_px, center=None):
    """Sum of Zernike polynomial terms for wavefront/aberration correction.

    coeffs: dict mapping (n, m) -> weight (radians), standard double-index
    Zernike notation (n >= |m|, n - |m| even). radius_px normalizes rho to the
    unit circle over which Zernike polynomials are defined; outside that
    circle the phase is set to 0 (no correction applied)."""
    x, y = pixel_grid(shape, center)
    rho = np.hypot(x, y) / radius_px
    phi = np.arctan2(y, x)
    inside = rho <= 1.0

    phase = np.zeros(shape, dtype=np.float64)
    for (n, m), weight in coeffs.items():
        radial = _zernike_radial(n, m, rho)
        angular = np.cos(m * phi) if m >= 0 else np.sin(-m * phi)
        phase = phase + weight * radial * angular
    phase[~inside] = 0.0
    return phase


def checkerboard_phase(shape, period_px, low=0.0, high=np.pi, center=None):
    """Two-level checkerboard, useful as a diffraction-efficiency/calibration
    test pattern (splits light into a symmetric grid of diffraction orders)."""
    x, y = pixel_grid(shape, center)
    tile = (np.floor(x / period_px).astype(np.int64) + np.floor(y / period_px).astype(np.int64)) % 2
    return np.where(tile == 0, low, high)


def random_phase(shape, seed=None):
    """Uniform random phase in [0, 2*pi) — diffuser / calibration pattern."""
    rng = np.random.default_rng(seed)
    return rng.uniform(0, 2 * np.pi, size=shape)
