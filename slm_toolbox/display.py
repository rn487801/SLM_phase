"""Send a rendered pattern to the SLM over HDMI.

An SLM connected via HDMI shows up to Windows as an ordinary secondary
monitor, so "projecting" a pattern is just: enumerate monitors, open a
borderless window positioned exactly over the SLM's monitor, and display the
rendered grayscale frame in it *without any resampling* — resizing a phase
pattern would interpolate phase values between pixels and corrupt the
hologram, so the pattern's pixel dimensions should match the SLM's native
resolution (1920x1080 is the common case and is this project's default).

Windows-only (uses ctypes + user32.dll monitor enumeration).
"""

import ctypes

import numpy as np
import tkinter as tk
from PIL import Image, ImageTk

DEFAULT_SLM_WIDTH = 1920
DEFAULT_SLM_HEIGHT = 1080


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * 32),
    ]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_RECT), ctypes.c_ssize_t
)

_MONITORINFOF_PRIMARY = 0x1


def list_monitors():
    """Enumerate connected monitors. Returns a list of dicts with x, y, width,
    height (in physical pixels), primary (bool), and device (adapter name).
    Order matches Windows' enumeration order; use the 'primary' flag to find
    the main display rather than assuming index 0 is it."""
    user32 = ctypes.windll.user32
    monitors = []

    def _callback(hmonitor, _hdc, _lprect, _lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        r = info.rcMonitor
        monitors.append({
            "x": r.left,
            "y": r.top,
            "width": r.right - r.left,
            "height": r.bottom - r.top,
            "primary": bool(info.dwFlags & _MONITORINFOF_PRIMARY),
            "device": info.szDevice,
        })
        return 1

    callback = _MONITORENUMPROC(_callback)
    user32.EnumDisplayMonitors(0, 0, callback, 0)
    return monitors


def default_slm_monitor(monitors):
    """Guess which monitor is the SLM: prefer the first non-primary monitor
    (an HDMI-connected SLM is normally the secondary display); fall back to
    the primary/only monitor if there's just one."""
    non_primary = [m for m in monitors if not m["primary"]]
    if non_primary:
        return non_primary[0]
    return monitors[0] if monitors else None


class ProjectorWindow:
    """Borderless, always-on-top window pinned over a monitor's full extent,
    showing a rendered grayscale pattern at native resolution (no resampling).
    Press Escape (with the projection window focused) to close it."""

    def __init__(self, master, monitor, gray_array, on_close=None):
        self.on_close = on_close
        self.top = tk.Toplevel(master)
        self.top.overrideredirect(True)
        self.top.geometry(f"{monitor['width']}x{monitor['height']}+{monitor['x']}+{monitor['y']}")
        self.top.configure(bg="black")
        self.top.attributes("-topmost", True)

        mode = "L" if gray_array.dtype == np.uint8 else "I;16"
        image = Image.fromarray(gray_array, mode=mode)
        self.photo = ImageTk.PhotoImage(image)
        self.label = tk.Label(self.top, image=self.photo, bg="black", bd=0, highlightthickness=0)
        self.label.pack(fill="both", expand=True)

        self.top.bind("<Escape>", lambda _e: self.close())

        # Force the window to the front. A single -topmost/focus_force isn't
        # always enough (Windows can ignore focus requests from a background
        # process), so also toggle -topmost off/on and lift() after the
        # window is actually mapped.
        self.top.lift()
        self.top.focus_force()
        self.top.after(50, self._raise_to_front)

    def _raise_to_front(self):
        self.top.attributes("-topmost", False)
        self.top.attributes("-topmost", True)
        self.top.lift()
        self.top.focus_force()

    def update_image(self, gray_array):
        mode = "L" if gray_array.dtype == np.uint8 else "I;16"
        image = Image.fromarray(gray_array, mode=mode)
        self.photo = ImageTk.PhotoImage(image)
        self.label.configure(image=self.photo)

    def close(self):
        if self.top.winfo_exists():
            self.top.destroy()
        if self.on_close is not None:
            self.on_close()
