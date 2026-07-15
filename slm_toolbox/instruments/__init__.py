"""Lab instrument drivers for automated optoelectronic measurements alongside
the SLM (slm_toolbox.api.SLM).

Design rules (so importing slm_toolbox never drags in hardware libraries and
so measurement scripts can be developed with no hardware attached):

- Heavy / vendor dependencies (pyvisa, the HIKROBOT MVS SDK, ...) are imported
  lazily inside connect()/open, NOT at module import. `import
  slm_toolbox.instruments` works on any machine with just numpy + pyserial.
- Every real driver has a matching mock in `mock.py` with the SAME public API,
  so a full measurement script (including SLM.run_efficiency_calibration, which
  takes a `measure_fn`) runs end-to-end against fakes for development/CI.
- Detector-type instruments (power meter, camera) expose `.measure_fn(...)`
  returning a plain `() -> float` callable, which is exactly what
  slm_toolbox.api.SLM.run_efficiency_calibration and measurement sweeps expect.

Modules:
    base          - Instrument base class (context manager, lazy-dep helper)
    elliptec      - Thorlabs Elliptec bus (ELLB/ELLC) + devices (ELL14 rotation,
                    ELL15) over the ASCII serial protocol
    power_meter   - Thorlabs PM100 power meter
    camera        - HIKROBOT (Hikvision MVS SDK) CMOS camera
    mock          - hardware-free fakes of all of the above
"""

from . import base, elliptec, power_meter, camera, mock
from .elliptec import ElliptecBus, ElliptecDevice, ELL14Rotation, ELL15Iris
from .power_meter import PM100
from .camera import HikrobotCamera

__all__ = [
    "base", "elliptec", "power_meter", "camera", "mock",
    "ElliptecBus", "ElliptecDevice", "ELL14Rotation", "ELL15Iris",
    "PM100", "HikrobotCamera",
]
