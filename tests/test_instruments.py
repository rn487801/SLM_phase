"""Head-less regression checks for slm_toolbox.instruments -- no hardware, no
vendor libraries. Verifies: (1) the package imports with only numpy/pyserial;
(2) real drivers raise a CLEAR ImportError (not a raw one) when their vendor
dep is absent; (3) the mocks implement the documented API and their
detector-type `measure_fn()` returns a plain float; (4) the mocks integrate
with the real SLM.run_efficiency_calibration pipeline.

Run: python tests/test_instruments.py   (exits nonzero on failure)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

failures = []


def check(name, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")
    if not condition:
        failures.append(name)


def main():
    import slm_toolbox.instruments as inst
    check("package imports with no vendor libs", hasattr(inst, "ELL14Rotation"))

    # Real drivers must give a clear ImportError when the vendor dep is missing.
    from slm_toolbox.instruments import ElliptecBus, ELL14Rotation, PM100, HikrobotCamera
    for name, thunk in [
        ("Elliptec", lambda: ELL14Rotation(ElliptecBus("COM4"))),
        ("PM100", lambda: PM100("USB0::MOCK")),
        ("Hikrobot", lambda: HikrobotCamera()),
    ]:
        try:
            thunk()
            raised = False
            msg = ""
        except ImportError as exc:
            raised, msg = True, str(exc)
        except Exception:
            raised, msg = False, ""
        # (If the vendor lib happens to be installed, importing succeeds and we
        # skip the "clear error" assertion for that one.)
        try:
            __import__({"Elliptec": "thorlabs_elliptec", "PM100": "pyvisa",
                        "Hikrobot": "MvCameraControl_class"}[name])
            installed = True
        except ImportError:
            installed = False
        if not installed:
            check(f"{name} driver: clear ImportError when dep missing",
                  raised and "is required" in msg)

    from slm_toolbox.instruments import mock

    # Elliptec bus + devices: two devices share one bus with distinct ids.
    bus = mock.MockElliptecBus("COM4", kind="ELLB")
    rot = mock.MockELL14Rotation(bus, device_id=1)
    iris = mock.MockELL15Iris(bus, device_id=2)
    rot.move_absolute(370)
    check("ELL14 wraps angle into [0,360)", abs(rot.get_position() - 10.0) < 1e-9)
    rot.move_relative(-15)
    check("ELL14 relative move", abs(rot.get_position() - (-5.0)) < 1e-9)
    iris.move_absolute(3.0)
    check("two devices, distinct device_id on one bus",
          rot.device_id == 1 and iris.device_id == 2 and abs(iris.get_position() - 3.0) < 1e-9)

    # Detector measure_fn() returns a plain float.
    pm = mock.MockPM100(wavelength_nm=1064, baseline=1e-3, noise=0)
    check("PM100 measure_fn returns float", isinstance(pm.measure_fn()(), float))
    cam = mock.MockHikrobotCamera(width=64, height=48)
    frame = cam.grab()
    check("camera grab returns 2-D uint8 frame",
          frame.shape == (48, 64) and frame.dtype == np.uint8)
    check("camera measure_fn returns float", isinstance(cam.measure_fn()(), float))

    # Context managers close.
    with mock.MockPM100() as p:
        pass
    check("context manager closes the instrument", p.closed)

    # Integration: mock power meter drives the real calibration pipeline and
    # recovers a synthetic ground-truth phase curve.
    from slm_toolbox import SLM
    with SLM(wavelength_nm=1064) as slm:
        def signal():
            g = slm._last_gray
            return 0.0 if g is None else float(np.sin(np.pi * int(g.max()) / 255.0) ** 2)
        pm2 = mock.MockPM100(wavelength_nm=1064, signal_fn=signal, noise=0)
        curve = slm.run_efficiency_calibration(measure_fn=pm2.measure_fn(), settle_s=0.0)
        truth = 2 * np.pi * (curve.gray / 255.0)
        check("mock PM drives SLM calibration to ~ground-truth curve",
              float(np.abs(curve.phase_rad - truth).max()) < 0.1)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
