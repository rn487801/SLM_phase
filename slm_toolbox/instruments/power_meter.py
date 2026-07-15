"""Thorlabs PM100 optical power meter.

Driven over VISA/SCPI (pyvisa), which is the universal path for the Thorlabs
PMxxx family -- the same SCPI command set works for PM100D / PM100USB / PM160 /
PM400, so this one class covers the PM100 the user asked about and its
siblings. (The existing `instruments codes/` power-meter wrapper used
pylablib's PM160 class instead; this is a lighter, model-agnostic
equivalent.) pyvisa is imported lazily.

The important method for automated SLM measurements is `measure_fn()`, which
returns a plain `() -> float` callable of power in watts -- exactly what
`slm_toolbox.api.SLM.run_efficiency_calibration(measure_fn=...)` and beam
sweeps expect.
"""

from .base import Instrument, lazy_import

_PIP_HINT = "pip install pyvisa (plus a VISA backend, e.g. NI-VISA or `pip install pyvisa-py`)"


class PM100(Instrument):
    """Thorlabs PM100 (and PM100D/PM100USB/PM160/PM400) power meter over
    VISA/SCPI.

    resource: VISA resource string, e.g.
        'USB0::0x1313::0x8078::P0005244::0::INSTR'
    (list candidates with `PM100.list_resources()`). Power reads are in
    WATTS; wavelength is set/read in nanometers.
    """

    def __init__(self, resource, wavelength_nm=None, autorange=True, timeout_ms=5000):
        self._pyvisa = lazy_import("pyvisa", _PIP_HINT, purpose="talk to a Thorlabs PM100 power meter")
        self._rm = self._pyvisa.ResourceManager()
        self._dev = self._rm.open_resource(resource)
        self._dev.timeout = timeout_ms
        if autorange:
            self._dev.write("SENS:POW:RANG:AUTO ON")
        if wavelength_nm is not None:
            self.set_wavelength_nm(wavelength_nm)

    @staticmethod
    def list_resources():
        """VISA resource strings visible to the system -- to find the meter's
        address. Requires pyvisa."""
        import importlib
        pyvisa = importlib.import_module("pyvisa")
        return list(pyvisa.ResourceManager().list_resources())

    def idn(self):
        return self._dev.query("*IDN?").strip()

    def set_wavelength_nm(self, wavelength_nm):
        """Set the correction wavelength (the meter needs this for a correct
        reading -- match it to your laser)."""
        self._dev.write(f"SENS:CORR:WAV {float(wavelength_nm)}")

    def get_wavelength_nm(self):
        return float(self._dev.query("SENS:CORR:WAV?"))

    def get_power(self):
        """Single power reading in WATTS."""
        return float(self._dev.query("MEAS:POW?"))

    def get_power_averaged(self, n=10):
        """Mean of n readings -- reduces flicker/noise for a stable sweep
        point (the SOP recommends averaging multiple frames per point)."""
        return sum(self.get_power() for _ in range(max(1, n))) / max(1, n)

    def measure_fn(self, averages=1):
        """Return a `() -> float` power-in-watts callable for
        SLM.run_efficiency_calibration / measurement sweeps. averages>1
        averages that many readings per call."""
        if averages > 1:
            return lambda: self.get_power_averaged(averages)
        return self.get_power

    def close(self):
        try:
            self._dev.close()
        except Exception:
            pass
        try:
            self._rm.close()
        except Exception:
            pass
