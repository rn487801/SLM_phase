from pylablib.devices.Thorlabs import PM160

class PowerMeter:
    """Wrapper for Thorlabs PM160 power meter."""

    def __init__(self, resource):
        """
        Initialize power meter.
        Example resource: 'USB0::0x1313::0x8078::P0005244::0::INSTR'
        """
        self.pm = PM160(resource)
        self.pm.open()
        self.pm.enable_autorange(True)

    def set_wavelength(self, wavelength_nm):
        """Set wavelength in nanometers."""
        self.pm.set_wavelength(wavelength_nm * 1e-9)  # convert to meters

    def get_power(self):
        """Return measured power in watts."""
        return self.pm.get_power()

    def get_status(self):
        """Return full instrument status (optional)."""
        return self.pm.get_full_status(include="all")

    def close(self):
        """Close connection safely."""
        try:
            self.pm.close()
        except Exception as e:
            print(f"Error closing power meter: {e}")
