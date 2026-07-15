from thorlabs_elliptec import ELLx, ELLError
import time

class RotationMount:
    """
    Wrapper for Thorlabs ELLx rotation stages (e.g. ELL14, ELL18).
    Supports homing, absolute/relative movement, blocking/non-blocking modes, and error handling.
    """
    
    def __init__(self, x=14, port="COM4", device_id=1):
        self.stage = ELLx(x=x, serial_port=port, device_id=device_id)
        """
        Initialize the rotation mount connection.

        Parameters
        ----------
        port : str or ELLx
            COM port (e.g., 'COM4') or an existing ELLx object to chain multiple devices.
        device_id : int
            Device ID assigned in the ELLO GUI.
        x : int
            Model number (usually 14 for ELL14, 18 for ELL18, etc.)
        """
    
    def home(self, blocking=True):
        """Move to home position."""
        self.stage.home(blocking=blocking)

   
    def move_to(self, angle, blocking=True):
        """Move to absolute angle."""
        angle = angle % 360  # safety wrap
        self.stage.move_absolute(angle, blocking=blocking)

    
    def move_by(self, delta, blocking=True):
        """Move relative to the current position (degrees)."""
        self.stage.move_relative(delta, blocking=blocking)

    
    def get_position(self):
        """Return the current position in degrees."""
        return self.stage.get_position()

    
    def is_moving(self):
        """Check whether motion is ongoing."""
        return self.stage.is_moving()

    
    def close(self):
        """Close connection."""
        self.stage.close()

