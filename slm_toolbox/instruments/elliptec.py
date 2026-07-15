"""Thorlabs Elliptec devices (ELL14 rotation mount, ELL15, ...) on a shared
serial bus (ELLB bus distributor / ELLC interface board).

How the hardware actually connects (important for the API shape here): an
ELLB (bus distributor) or ELLC (interface board) presents ONE USB serial
port to the host. One or more Elliptec motion devices sit on that bus, each
with a 1-hex-digit address (`device_id`, 0..15). So "controlling the
ELLB/ELLC" == opening its serial port; the ELL14/ELL15 are addressed on it.
That's the ElliptecBus (the port) + device-objects (addressed) split below --
matching the multi-drop pattern the existing lab code uses (chaining a shared
serial connection across devices by device_id).

Built on the `thorlabs_elliptec` package (the same one the existing
`instruments codes/` rotation-mount driver uses), imported lazily so this
module imports fine without it. Mock equivalents live in
`slm_toolbox.instruments.mock` for hardware-free development.
"""

from .base import Instrument, lazy_import

_PIP_HINT = "pip install thorlabs-elliptec"


class ElliptecBus(Instrument):
    """The serial interface an ELLB (bus distributor) or ELLC (interface
    board) presents to the host. Open it once, then attach device objects
    (ELL14Rotation, ELL15, ...) that share it by `device_id`.

    `kind` ("ELLB" | "ELLC") is documentation only -- both present the same
    serial port; the practical difference is that an ELLB fans the bus out to
    several devices (so device_id addressing matters), while an ELLC is
    typically one device. The host-side code is identical either way.
    """

    def __init__(self, port="COM4", kind="ELLB"):
        self.port = port
        self.kind = kind
        # The first device created opens the physical port; later devices are
        # handed that first ELLx as their `serial_port` so they share the bus
        # (the pattern the existing lab notebooks use). We hold it here.
        self._shared_conn = None

    def _serial_port_arg(self):
        """What to pass as ELLx(serial_port=...): the shared open connection
        if one exists yet, else the port string for the first device to open."""
        return self._shared_conn if self._shared_conn is not None else self.port

    def _register(self, ellx):
        if self._shared_conn is None:
            self._shared_conn = ellx

    def close(self):
        if self._shared_conn is not None:
            try:
                self._shared_conn.close()
            except Exception:
                pass
            self._shared_conn = None


class ElliptecDevice(Instrument):
    """Generic Elliptec device on a bus. `model` is the Elliptec model number
    (14 for ELL14, 15 for ELL15, ...) passed to `thorlabs_elliptec.ELLx` as
    its `x=`. Position units are whatever the device reports natively (degrees
    for a rotary mount); the library handles the pulse<->unit conversion from
    the device's own calibration."""

    def __init__(self, bus, model, device_id=1):
        self.bus = bus
        self.model = model
        self.device_id = device_id
        elliptec = lazy_import("thorlabs_elliptec", _PIP_HINT, purpose="control a Thorlabs Elliptec device")
        self._stage = elliptec.ELLx(x=model, serial_port=bus._serial_port_arg(), device_id=device_id)
        bus._register(self._stage)

    def home(self, blocking=True):
        self._stage.home(blocking=blocking)

    def move_absolute(self, position, blocking=True):
        self._stage.move_absolute(position, blocking=blocking)

    def move_relative(self, delta, blocking=True):
        self._stage.move_relative(delta, blocking=blocking)

    def get_position(self):
        return self._stage.get_position()

    def is_moving(self):
        return self._stage.is_moving()

    def close(self):
        try:
            self._stage.close()
        except Exception:
            pass


class ELL14Rotation(ElliptecDevice):
    """ELL14 rotation mount. Position is in DEGREES; absolute moves are
    wrapped into [0, 360)."""

    def __init__(self, bus, device_id=1):
        super().__init__(bus, model=14, device_id=device_id)

    def move_absolute(self, angle_deg, blocking=True):
        super().move_absolute(angle_deg % 360.0, blocking=blocking)


class ELL15Iris(ElliptecDevice):
    """ELL15 (used here as a motorized iris). Uses the same Elliptec protocol
    via `ELLx(x=15)`. NOTE: ELL15 is not a device this project has been able
    to confirm against a datasheet, and its position UNIT/semantics (an
    aperture/linear value vs. degrees) should be verified on first hardware
    connection -- `get_position()` returns whatever the device's own
    calibration reports. Motion API is otherwise identical to any Elliptec
    device."""

    def __init__(self, bus, device_id=2):
        super().__init__(bus, model=15, device_id=device_id)
