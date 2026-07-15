"""Example: camera-in-the-loop WAVEFRONT self-correction (sensorless adaptive
optics), runnable with NO hardware. A hidden aberration is injected into the
simulated optics; an SPGD loop drives the camera image-sharpness metric back up
by finding the Zernike correction that cancels it -- self-calibrating the phase
for the current wavelength/optics with only the CMOS camera as feedback.

The 'camera' here is a SimFeedbackCamera whose frames are the simulated
far-field of the SLM's current pattern, so the loop provably converges. For
real use, swap it for a real camera -- nothing else changes:
    from slm_toolbox.instruments import HikrobotCamera
    cam = HikrobotCamera(device_index=0, exposure_us=5000)

(Camera-read gray->phase Method C calibration is also supported -- point a
power-meter-style `measure_fn` at the camera with the ROI on the +1 diffraction
order, e.g. `slm.run_efficiency_calibration(measure_fn=cam.measure_fn(roi=...))`
where `roi` brackets the first order, NOT the zero order. See
examples/instruments_measurement_example.py for the measure_fn pattern.)

Run: python examples/self_calibration_example.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slm_toolbox import SLM, feedback, autocalibrate, patterns
from slm_toolbox.instruments import mock


def main():
    with SLM(wavelength_nm=1064) as slm:
        # A hidden aberration the loop doesn't know about (astigmatism + coma +
        # defocus), injected into the simulated optics.
        hidden = {(2, 2): 2.2, (3, 1): 1.5, (2, 0): 1.3}
        cam = mock.SimFeedbackCamera(slm, aberration_coeffs=hidden, sim_size=96, cam_size=64)
        sharpness = lambda: feedback.sharpness(cam.grab())

        slm.display_phase(np.zeros(slm.shape), settle_s=0.0)
        before = sharpness()

        terms = [(2, 2), (2, -2), (3, 1), (3, -1), (2, 0)]
        print("Self-correcting wavefront (SPGD on camera sharpness)...")
        correction, history = autocalibrate.optimize_zernike(
            slm, sharpness, terms, n_iter=80, gain=3.0, sigma=0.5, seed=1, settle_s=0.0)
        slm.display_phase(patterns.zernike_phase(slm.shape, correction, radius_px=min(slm.shape) / 2),
                          settle_s=0.0)
        after = sharpness()

        print(f"  sharpness {before:.4g} -> {after:.4g}  ({after/before:.1f}x)")
        print("  hidden aberration (rad):     ", {t: hidden[t] for t in hidden})
        print("  recovered correction (rad):  ",
              {t: round(c, 2) for t, c in correction.items() if abs(c) > 0.2})
        print("  (correction ~ negated hidden -> the loop found the aberration)")

    print("Done.")


if __name__ == "__main__":
    main()
