from pylablib.devices.Thorlabs import MFF
import time

class FlipMount:
    """Wrapper for Thorlabs MFF flip mount control."""

    def __init__(self, serial_number):
        """Initialize the flip mount using its USB serial number."""
        self.mount = MFF(serial_number)
        self.mount.open()

    def move_to_state(self, state):
        """
        Move to position:
        0 = block the beam
        1 = unblock (remove) the mount.
        """
        self.mount.move_to_state(state)
        time.sleep(0.5)  # small delay for mechanical movement

    def get_state(self):
        """Return current flip state (0 or 1)."""
        return self.mount.get_state()

    def close(self):
        """Close connection safely."""
        try:
            self.mount.close()
        except Exception as e:
            print(f"Error closing flip mount: {e}")
