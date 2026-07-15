"""Hardware-free mocks of every driver, with identical public APIs.

Purpose: develop and test a full measurement script -- including
`SLM.run_efficiency_calibration(measure_fn=...)` -- with no instruments and no
vendor libraries attached. Swap `Mock*` for the real class when you're at the
bench; nothing else in the script changes.

The detector mocks (MockPM100, MockHikrobotCamera) accept an optional
`signal_fn` callable so a demo can feed them a physically-meaningful reading
(e.g. a simulated diffraction efficiency) instead of a constant.
"""

import numpy as np

from .base import Instrument


class MockElliptecBus(Instrument):
    def __init__(self, port="COM_MOCK", kind="ELLB"):
        self.port = port
        self.kind = kind
        self.closed = False

    def _serial_port_arg(self):
        return self.port

    def _register(self, dev):
        pass

    def close(self):
        self.closed = True


class MockElliptecDevice(Instrument):
    def __init__(self, bus, model, device_id=1):
        self.bus = bus
        self.model = model
        self.device_id = device_id
        self.position = 0.0
        self._moving = False
        self.closed = False

    def home(self, blocking=True):
        self.position = 0.0

    def move_absolute(self, position, blocking=True):
        self.position = float(position)

    def move_relative(self, delta, blocking=True):
        self.position += float(delta)

    def get_position(self):
        return self.position

    def is_moving(self):
        return self._moving

    def close(self):
        self.closed = True


class MockELL14Rotation(MockElliptecDevice):
    def __init__(self, bus, device_id=1):
        super().__init__(bus, model=14, device_id=device_id)

    def move_absolute(self, angle_deg, blocking=True):
        self.position = float(angle_deg) % 360.0


class MockELL15Iris(MockElliptecDevice):
    def __init__(self, bus, device_id=2):
        super().__init__(bus, model=15, device_id=device_id)


class MockPM100(Instrument):
    """signal_fn: optional () -> float giving the 'true' power (watts) this
    reading should report; default is a constant `baseline`. Gaussian read
    noise (`noise`) is added on top so averaging behaves like real hardware."""

    def __init__(self, resource="MOCK::PM100", wavelength_nm=None, signal_fn=None,
                 baseline=1e-3, noise=1e-5, seed=0):
        self.resource = resource
        self.wavelength_nm = wavelength_nm
        self._signal_fn = signal_fn
        self._baseline = baseline
        self._noise = noise
        self._rng = np.random.default_rng(seed)
        self.closed = False

    def idn(self):
        return "MOCK,PM100,0,0"

    def set_wavelength_nm(self, wavelength_nm):
        self.wavelength_nm = wavelength_nm

    def get_wavelength_nm(self):
        return self.wavelength_nm

    def get_power(self):
        base = self._signal_fn() if self._signal_fn is not None else self._baseline
        return float(base + self._rng.normal(0, self._noise))

    def get_power_averaged(self, n=10):
        return sum(self.get_power() for _ in range(max(1, n))) / max(1, n)

    def measure_fn(self, averages=1):
        if averages > 1:
            return lambda: self.get_power_averaged(averages)
        return self.get_power

    def close(self):
        self.closed = True


class SimFeedbackCamera(Instrument):
    """A 'camera' whose frames are the SIMULATED far-field (focal-plane
    diffraction, via slm_toolbox.simulate) of whatever the SLM is currently
    displaying, plus an optional hidden aberration. Same grab()/measure_fn API
    as MockHikrobotCamera, so it drops into a real feedback/self-calibration
    loop -- but because the optics are simulated, the loop is fully testable
    with no hardware, and provably converges (e.g. an SPGD Zernike optimizer
    removes the hidden aberration and re-sharpens the spot).

    slm: an api.SLM (read via its `_last_phase`, the wrapped phase last
        rendered). aberration_coeffs: {(n,m): rad} Zernike terms secretly added
        to the pupil (the thing a self-calibration loop should discover and
        cancel). sim_size: pupil sampling for the FFT (small = fast loop).
    """

    def __init__(self, slm, aberration_coeffs=None, sim_size=96, cam_size=64,
                 illumination_waist_frac=0.5, noise=0.0, seed=0):
        self.slm = slm
        self.aberration_coeffs = aberration_coeffs or {}
        self.sim_size = sim_size
        self.cam_size = cam_size
        self.illumination_waist_frac = illumination_waist_frac
        self.noise = noise
        self._rng = np.random.default_rng(seed)
        self.closed = False

    def _downsample(self, phase):
        # Crop the CENTERED square (side = min(h,w)) before resampling to a
        # square sim grid. The Zernike unit disk (radius min(shape)/2, centered)
        # is inscribed in this square, so cropping it keeps the phase geometry
        # undistorted -- resampling a non-square panel straight to a square grid
        # would anisotropically stretch it and break aberration<->correction
        # matching. (Real hardware has no downsample; this only keeps the
        # simulation faithful for non-square SLMs.)
        h, w = phase.shape
        s = min(h, w)
        y0, x0 = (h - s) // 2, (w - s) // 2
        square = phase[y0:y0 + s, x0:x0 + s]
        idx = np.linspace(0, s - 1, self.sim_size).astype(int)
        return square[np.ix_(idx, idx)]

    def grab(self):
        from .. import simulate, patterns  # lazy: core deps, avoids any import cycle
        n = self.sim_size
        if self.slm._last_phase is not None:
            pupil_phase = self._downsample(self.slm._last_phase)
        else:
            pupil_phase = np.zeros((n, n))
        if self.aberration_coeffs:
            pupil_phase = pupil_phase + patterns.zernike_phase(
                (n, n), self.aberration_coeffs, radius_px=n / 2.0)
        waist_px = self.illumination_waist_frac * n
        illum = simulate.gaussian_illumination((n, n), waist_m=waist_px, pixel_pitch_m=1.0)
        intensity, _ = simulate.simulate_far_field(pupil_phase, wavelength_m=1.0, pixel_pitch_m=1.0,
                                                    amplitude=illum, pad_factor=2)
        # crop the central cam_size window
        fh, fw = intensity.shape
        c = self.cam_size
        y0, x0 = fh // 2 - c // 2, fw // 2 - c // 2
        crop = intensity[y0:y0 + c, x0:x0 + c]
        if self.noise:
            crop = np.clip(crop + self._rng.normal(0, self.noise, crop.shape), 0, None)
        peak = crop.max()
        norm = crop / peak if peak > 0 else crop
        return (norm * 255).astype(np.uint8)

    def measure_fn(self, roi=None, reducer="sum", frame_averages=1):
        reduce = (np.sum if reducer == "sum" else np.max)

        def _measure():
            acc = 0.0
            for _ in range(max(1, frame_averages)):
                frame = self.grab()
                if roi is not None:
                    x0, y0, x1, y1 = roi
                    frame = frame[y0:y1, x0:x1]
                acc += float(reduce(frame))
            return acc / max(1, frame_averages)

        return _measure

    def close(self):
        self.closed = True


class MockHikrobotCamera(Instrument):
    """grab() returns a synthetic (height, width) uint8 frame: a Gaussian spot
    on a dark background. If `signal_fn` is given, its float return scales the
    spot's peak brightness (so a measure_fn tracks a simulated signal)."""

    def __init__(self, device_index=0, width=640, height=480, exposure_us=None,
                 signal_fn=None, spot_xy=None, spot_sigma=40.0, seed=0):
        self.device_index = device_index
        self.width = width
        self.height = height
        self.exposure_us = exposure_us
        self._signal_fn = signal_fn
        self._spot_xy = spot_xy or (width // 2, height // 2)
        self._spot_sigma = spot_sigma
        self._rng = np.random.default_rng(seed)
        self.closed = False

    def set_exposure_us(self, exposure_us):
        self.exposure_us = exposure_us

    def set_gain(self, gain_db):
        pass

    def grab(self):
        y, x = np.indices((self.height, self.width))
        cx, cy = self._spot_xy
        r2 = (x - cx) ** 2 + (y - cy) ** 2
        peak = self._signal_fn() if self._signal_fn is not None else 1.0
        spot = peak * np.exp(-r2 / (2 * self._spot_sigma ** 2))
        noise = self._rng.normal(0, 0.01, size=spot.shape)
        frame = np.clip((spot + noise) * 255, 0, 255).astype(np.uint8)
        return frame

    def measure_fn(self, roi=None, reducer="sum", frame_averages=1):
        reduce = (np.sum if reducer == "sum" else np.max)

        def _measure():
            acc = 0.0
            for _ in range(max(1, frame_averages)):
                frame = self.grab()
                if roi is not None:
                    x0, y0, x1, y1 = roi
                    frame = frame[y0:y1, x0:x1]
                acc += float(reduce(frame))
            return acc / max(1, frame_averages)

        return _measure

    def close(self):
        self.closed = True
