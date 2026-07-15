"""Example: a full automated optoelectronic measurement combining the SLM
with lab instruments (Thorlabs Elliptec rotation mount + PM100 power meter +
HIKROBOT camera).

Two phases, both driven end-to-end by the instruments:
  1. Automated calibration -- gray sweep read back by the power meter.
  2. An OAM-charge sweep imaged by the camera (integrated spot intensity per
     vortex charge), with a polarizer rotated by the Elliptec mount.

Runs standalone with MOCK instruments (no hardware, no vendor libraries), so
you can see the shape of a real measurement script. To run it for real, flip
USE_MOCK to False and set the real port / VISA-resource / device strings --
nothing else in the script changes (the real and mock classes share the same
API).

Run: python examples/instruments_measurement_example.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slm_toolbox import SLM

USE_MOCK = True
WAVELENGTH_NM = 1064

ELLIPTEC_PORT = "COM4"                                  # ELLB/ELLC serial port
PM100_RESOURCE = "USB0::0x1313::0x8078::P0005244::0::INSTR"  # PM100 VISA address


def make_instruments(slm):
    if USE_MOCK:
        from slm_toolbox.instruments import mock
        # mock power meter reports sin^2(dphi/2) for the grating on the SLM,
        # so run_efficiency_calibration below produces a realistic sweep.
        def efficiency_signal():
            g = slm._last_gray
            if g is None:
                return 0.0
            dphi = 2 * np.pi * (int(g.max()) / 255.0)
            return float(np.sin(dphi / 2) ** 2)
        pm = mock.MockPM100(wavelength_nm=WAVELENGTH_NM, signal_fn=efficiency_signal, noise=1e-4)
        bus = mock.MockElliptecBus(ELLIPTEC_PORT)
        rot = mock.MockELL14Rotation(bus, device_id=1)
        cam = mock.MockHikrobotCamera(width=320, height=240, spot_sigma=25)
        return pm, bus, rot, cam
    else:
        from slm_toolbox.instruments import PM100, ElliptecBus, ELL14Rotation, HikrobotCamera
        pm = PM100(PM100_RESOURCE, wavelength_nm=WAVELENGTH_NM)
        bus = ElliptecBus(ELLIPTEC_PORT, kind="ELLB")
        rot = ELL14Rotation(bus, device_id=1)
        cam = HikrobotCamera(device_index=0, exposure_us=5000)
        return pm, bus, rot, cam


def main():
    with SLM(wavelength_nm=WAVELENGTH_NM) as slm:
        pm, bus, rot, cam = make_instruments(slm)
        try:
            # 1) Automated calibration driven by the power meter (Method C).
            print("Calibrating (gray-level sweep, power meter readback)...")
            slm.run_efficiency_calibration(measure_fn=pm.measure_fn(averages=3), settle_s=0.05)
            print("  ->", slm.calibration_status())

            # 2) OAM-charge sweep imaged by the camera, polarizer at 0 deg.
            #    measure_fn integrates a central ROI around the beam.
            rot.home()
            rot.move_absolute(0.0)
            read_spot = cam.measure_fn(roi=(120, 80, 200, 160), reducer="sum", frame_averages=3)
            results = []
            for l in range(-3, 4):
                slm.display_phase(slm.vortex(l), slm.grating(period_px=12), settle_s=0.05)
                counts = read_spot()
                results.append((l, counts))
                print(f"  l={l:+d}  polarizer={rot.get_position():.0f} deg  "
                      f"integrated counts={counts:.0f}")
        finally:
            cam.close()
            rot.close()
            bus.close()
            pm.close()

    print("Done.")


if __name__ == "__main__":
    main()
