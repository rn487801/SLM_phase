"""Head-less checks for camera-feedback analysis (slm_toolbox.feedback) and
closed-loop self-calibration (slm_toolbox.autocalibrate). No hardware, no GUI:
the 'camera' is a SimFeedbackCamera whose frames are the simulated far-field of
the SLM's current pattern, so the SPGD loop is a genuine end-to-end test --
inject a hidden aberration, confirm the loop recovers the exact correction.

Run: python tests/test_autocalibrate.py   (exits nonzero on failure)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slm_toolbox import feedback, autocalibrate, patterns, compose
from slm_toolbox.instruments import mock

failures = []


def check(name, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")
    if not condition:
        failures.append(name)


class TinySLM:
    """Minimal SLM duck-type for fast testing: just .shape + .display_phase
    storing the wrapped phase (what SimFeedbackCamera/autocalibrate use)."""

    def __init__(self, size=96):
        self.shape = (size, size)
        self._last_phase = None

    def display_phase(self, *phases, weights=None, settle_s=0.0):
        total = compose.sum_phases(*phases) if phases else np.zeros(self.shape)
        self._last_phase = compose.wrap_phase(total)


def gaussian_frame(sigma, size=100):
    y, x = np.indices((size, size))
    r2 = (x - size / 2) ** 2 + (y - size / 2) ** 2
    return np.clip(np.exp(-r2 / (2 * sigma ** 2)) * 255, 0, 255).astype(np.uint8)


def main():
    # --- feedback image analysis ---
    tight, broad = gaussian_frame(6), gaussian_frame(20)
    check("sharpness higher for a tighter spot",
          feedback.sharpness(tight) > feedback.sharpness(broad))
    spot = feedback.find_spot(tight)
    check("find_spot centroid ~ image center",
          abs(spot["centroid_x"] - 50) < 2 and abs(spot["centroid_y"] - 50) < 2)
    check("find_spot width smaller for tighter spot",
          feedback.find_spot(tight)["width_x"] < feedback.find_spot(broad)["width_x"])
    roi = feedback.auto_roi(tight, margin=5)
    check("auto_roi brackets the spot center", roi[0] < 50 < roi[2] and roi[1] < 50 < roi[3])
    sat = gaussian_frame(6).copy()
    sat[:] = 255
    check("saturation_fraction detects a fully-clipped frame",
          feedback.saturation_fraction(sat) == 1.0)

    # --- closed-loop self-calibration convergence ---
    slm = TinySLM(96)
    hidden = {(2, 2): 2.5, (3, 1): 1.8, (2, 0): 1.5, (3, -1): -1.2}
    cam = mock.SimFeedbackCamera(slm, aberration_coeffs=hidden, sim_size=96, cam_size=64, noise=0.0)
    metric = lambda: feedback.sharpness(cam.grab())

    slm.display_phase(np.zeros(slm.shape))
    s_before = metric()

    terms = [(2, 2), (2, -2), (3, 1), (3, -1), (2, 0), (4, 0)]
    best, history = autocalibrate.optimize_zernike(slm, metric, terms, n_iter=150, gain=3.0,
                                                    sigma=0.5, seed=1, settle_s=0.0)
    slm.display_phase(patterns.zernike_phase(slm.shape, best, radius_px=48))
    s_after = metric()

    check("self-calibration improves sharpness >2x", s_after > 2 * s_before)
    check("SPGD history is non-decreasing (running best)",
          all(b >= a - 1e-9 for a, b in zip(history, history[1:])))
    ok = all(abs(best[t] - (-hidden[t])) < 0.4 for t in hidden)
    check("recovered correction ~ negated hidden aberration (within 0.4 rad)", ok)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
