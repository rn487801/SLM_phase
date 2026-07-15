"""Example: using slm_toolbox.api.SLM in an automated optoelectronic
measurement script. Two scenarios: an automated Method C calibration run
against a (fake, in this example) power meter, then a vortex-charge sweep
logging a (fake) reading at each step.

Replace `fake_power_meter_reading()` with your real instrument's read call
(e.g. a Thorlabs PM100D, a lock-in amplifier channel, a DAQ analog input --
anything returning a scalar). This script runs standalone (no real SLM
required) so you can see the shape of a real measurement script; swap in
real instrument calls to use it for real.

Run: python examples/api_measurement_example.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slm_toolbox import SLM


def fake_power_meter_reading():
    """Stand-in for e.g. `power_meter.read()`. Replace with your instrument."""
    import random
    return random.uniform(0.0, 1.0)


def main():
    with SLM(wavelength_nm=1064) as slm:
        print(slm)
        print("Calibration status before:", slm.calibration_status())

        # 1) Automated calibration (calibration_SOP.md Method C) -- comment
        #    this out once you've calibrated for real and saved a curve, or
        #    it'll happily recompute/overwrite it on every run.
        curve = slm.run_efficiency_calibration(measure_fn=fake_power_meter_reading, settle_s=0.05)
        print("Calibration saved:", curve.notes)
        print("Calibration status after:", slm.calibration_status())

        # 2) A real measurement sweep: vortex charge l = -3..3, forked with a
        #    steering grating so each order lands somewhere you can measure it.
        results = []
        for l in range(-3, 4):
            slm.display_phase(slm.vortex(l), slm.grating(period_px=12), settle_s=0.05)
            reading = fake_power_meter_reading()
            results.append((l, reading))
            print(f"l={l:+d}  reading={reading:.4f}")

        slm.blank()

    print("Results:", results)


if __name__ == "__main__":
    main()
