"""Shared instrument base + a lazy-import helper.

The existing lab drivers in `instruments codes/` use no common base class (each
is a bare wrapper with __init__/verb-methods/close). We add a thin base purely
for two things worth having in automated measurement scripts: guaranteed
cleanup via context-manager support, and a single clear error when a vendor
dependency isn't installed (instead of a raw ImportError deep in a driver).
Per-device method names still match the existing drivers' conventions
(get_power, move_absolute, home, close, ...).
"""

import importlib


def lazy_import(module_name, pip_hint=None, purpose=None):
    """Import a heavy/vendor module on demand, with a clear actionable error
    if it's missing -- so `import slm_toolbox.instruments` works on any
    machine (numpy + pyserial only) and the vendor dep is only required when
    you actually open that instrument."""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        bits = [f"'{module_name}' is required"]
        if purpose:
            bits.append(f"to {purpose}")
        bits.append("but is not installed.")
        if pip_hint:
            bits.append(f"Install it with: {pip_hint}")
        raise ImportError(" ".join(bits)) from exc


class Instrument:
    """Base for all drivers: context-manager cleanup + a no-op close() so
    subclasses only override what they need."""

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
