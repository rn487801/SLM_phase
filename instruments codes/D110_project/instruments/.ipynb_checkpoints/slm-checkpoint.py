import HEDS
from hedslib.heds_types import *

class SLMController:
    """Control HOLOEYE SLM with basic vortex-phase functions."""

    def __init__(self, sdk_version=(4, 0)):
        """
        Initialize the SLM SDK and open the first available device.
        sdk_version : tuple, default (4, 0)
            (major, minor) version of the HOLOEYE SDK to initialize.
        """
        # Initialize SDK
        err = HEDS.SDK.Init(*sdk_version)
        if err != HEDSERR_NoError:
            raise RuntimeError(f"SDK init failed: {HEDS.SDK.ErrorString(err)}")

        # Initialize SLM
        self.slm = HEDS.SLM.Init("", True, 0.0)
        if self.slm.errorCode() != HEDSERR_NoError:
            raise RuntimeError(f"SLM init failed: {HEDS.SDK.ErrorString(self.slm.errorCode())}")

        # Optional: place the preview on secondary monitor
        try:
            self.slm.preview().autoplaceLayoutOnSecondaryMonitor()
        except Exception as e:
            print(f"Preview placement skipped: {e}")

        print("SLM initialized successfully.")

    # --- Core function ---
    def set_OAM(self, l, shift_x=300, shift_y=0):
        """
        Display a vortex phase pattern on the SLM.
        Parameters
        ----------
        l : int
            Topological charge of the vortex (OAM number).
        shift_x : int
            Horizontal shift from the center in pixels.
        shift_y : int
            Vertical shift from the center in pixels.
        """
        err = self.slm.showVortex(l, centerX=shift_x, centerY=shift_y)
        if err != HEDSERR_NoError:
            raise RuntimeError(f"Failed to set vortex: {HEDS.SDK.ErrorString(err)}")
        print(f"Vortex with l={l} shown at ({shift_x}, {shift_y}).")

    def show_blank(self):
        """Clear the display (useful for resetting)."""
        err = self.slm.showBlank()
        if err != HEDSERR_NoError:
            raise RuntimeError(f"Failed to blank SLM: {HEDS.SDK.ErrorString(err)}")
        print("SLM display blanked.")

    def close(self):
        """Close the SLM connection and free resources."""
        err = self.slm.close()
        if err != HEDSERR_NoError:
            print(f"Warning: SLM close returned {HEDS.SDK.ErrorString(err)}")
        HEDS.SDK.Release()
        print("SLM connection closed.")
