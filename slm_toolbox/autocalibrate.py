"""Closed-loop, camera-in-the-loop self-calibration of the SLM phase.

This is "sensorless adaptive optics": show a phase, image the result with the
camera, reduce the image to a scalar quality metric (slm_toolbox.feedback), and
iteratively adjust the phase to maximize it -- correcting the system's
aberrations (per wavelength) with no wavefront sensor, just the CMOS camera.

The optimizer is SPGD (Stochastic Parallel Gradient Descent), the standard
robust algorithm for this: each step perturbs ALL parameters at once by a
random +-delta, measures the metric at +delta and -delta, and steps along the
finite-difference gradient estimate. It scales to many modes and tolerates
noise far better than per-coordinate hill-climbing.

Nothing here needs hardware to TEST: point `measure_metric` at a
SimFeedbackCamera (slm_toolbox.instruments.mock) whose frames are the simulated
far-field of the SLM's current pattern, and the loop provably converges (e.g.
removes an injected aberration). Swap in a real camera's frame for real use.
"""

import numpy as np

from . import patterns, compose


def spgd(apply_and_measure, x0, n_iter=60, gain=3.0, sigma=0.3, seed=0, maximize=True,
         normalize=True, sigma_decay=0.99, on_step=None):
    """Generic SPGD optimizer.

    apply_and_measure(x) -> float: apply the parameter vector x to the SLM
        (display the corresponding phase), read the camera, and return the
        scalar metric. Called twice per iteration (at x+dx and x-dx).
    x0: initial parameter vector. sigma: perturbation size. gain: step size.
    normalize=True uses the NORMALIZED SPGD update (step ~ gain * (J+ - J-) /
        (|J+| + |J-|) * dx), which is scale-invariant in the metric -- so the
        same gain works whether the metric is ~0.03 or ~3000, avoiding the
        gain-vs-metric-magnitude tuning trap. sigma_decay anneals the
        perturbation each step for finer late-stage convergence.
    Returns (best_x, history) of the running-best metric per iteration.
    Set maximize=False to minimize."""
    rng = np.random.default_rng(seed)
    x = np.array(x0, dtype=np.float64)
    sign = 1.0 if maximize else -1.0
    s = sigma

    best_x = x.copy()
    best_j = sign * apply_and_measure(x)
    history = [sign * best_j]

    for i in range(n_iter):
        dx = s * rng.choice([-1.0, 1.0], size=x.shape)
        j_plus = sign * apply_and_measure(x + dx)
        j_minus = sign * apply_and_measure(x - dx)
        diff = j_plus - j_minus
        if normalize:
            step = gain * (diff / (abs(j_plus) + abs(j_minus) + 1e-12)) * dx
        else:
            step = gain * diff * dx
        x = x + step
        j_here = sign * apply_and_measure(x)
        if j_here > best_j:
            best_j, best_x = j_here, x.copy()
        history.append(sign * best_j)
        if on_step is not None:
            on_step(i, x, sign * j_here)
        s *= sigma_decay

    return best_x, history


def optimize_zernike(slm, measure_metric, terms, base_phase=None, radius_px=None,
                     n_iter=60, gain=1.0, sigma=0.3, seed=0, settle_s=0.05):
    """Camera-feedback wavefront self-correction: find the Zernike-coefficient
    vector (over `terms`) that, added to `base_phase`, maximizes a camera
    metric -- i.e. the aberration correction for the current wavelength/optics.

    slm: an slm_toolbox.api.SLM (or anything with .shape and .display_phase).
    measure_metric() -> float: grab a frame and reduce it, e.g.
        `lambda: feedback.sharpness(cam.grab())`.
    terms: list of (n, m) Zernike indices to optimize (piston (0,0) / tilt are
        usually excluded -- tilt just steers, doesn't sharpen).
    base_phase: the pattern to correct on top of (e.g. slm.lens(f) to sharpen a
        focus); defaults to a flat phase.
    Returns (best_coeffs dict {(n,m): rad}, history)."""
    if radius_px is None:
        radius_px = min(slm.shape) / 2.0
    if base_phase is None:
        base_phase = np.zeros(slm.shape, dtype=np.float64)

    # Precompute each Zernike term's unit-coefficient phase ONCE. Zernike phase
    # is linear in the coefficients, so every SPGD step is then just a weighted
    # sum of these arrays -- far cheaper than recomputing the polynomials over
    # the full panel hundreds of times.
    basis = [patterns.zernike_phase(slm.shape, {t: 1.0}, radius_px=radius_px) for t in terms]

    def apply_and_measure(coeff_vec):
        correction = base_phase.copy()
        for c, b in zip(coeff_vec, basis):
            correction = correction + c * b
        slm.display_phase(correction, settle_s=settle_s)
        return measure_metric()

    x0 = np.zeros(len(terms))
    best_x, history = spgd(apply_and_measure, x0, n_iter=n_iter, gain=gain, sigma=sigma,
                           seed=seed, maximize=True)
    return {t: float(c) for t, c in zip(terms, best_x)}, history


def optimize_scalar(slm, measure_metric, make_phase, x0, bounds=None,
                    n_iter=40, gain=1.0, sigma=1.0, seed=0, settle_s=0.05):
    """Optimize a few free scalar parameters of an arbitrary phase via SPGD --
    e.g. auto-focus (find the lens focal length that maximizes sharpness) or
    auto-align a beam-steering offset. make_phase(x_vec) -> phase array;
    x0 is the starting parameter vector. Returns (best_x, history)."""
    def apply_and_measure(x):
        if bounds is not None:
            x = np.clip(x, [b[0] for b in bounds], [b[1] for b in bounds])
        slm.display_phase(make_phase(x), settle_s=settle_s)
        return measure_metric()

    return spgd(apply_and_measure, np.array(x0, dtype=np.float64), n_iter=n_iter,
                gain=gain, sigma=sigma, seed=seed, maximize=True)
