"""HIKROBOT (Hikvision machine-vision) CMOS camera via the MVS SDK.

HIKROBOT cameras are driven through the MVS SDK's Python bindings
(`MvCameraControl_class` et al.), which ship in the SDK's `MvImport` folder.
That folder must be installed (MVS software) and importable -- put it on
PYTHONPATH, or set the `MVCAM_COMMON_RUNENV` the installer configures. Those
modules are imported lazily here so this file imports fine without them.

This driver was written against the standard MVS Python sample flow but could
NOT be tested against real hardware in-repo -- treat it as needing a bench
check on first connection (especially pixel-format/stride handling for your
specific sensor). The mock in `slm_toolbox.instruments.mock` (synthetic
Gaussian-spot frames) lets you develop measurement scripts without it.

For automated SLM measurements the key method is `measure_fn(roi=...)`, a
`() -> float` returning integrated intensity over a region -- e.g. to read a
diffraction-order spot's brightness as `SLM.run_efficiency_calibration`'s
measure_fn instead of a power meter.
"""

import numpy as np

from .base import Instrument, lazy_import

_IMPORT_HINT = ("the HIKROBOT MVS SDK Python bindings (install MVS, then add its 'MvImport' "
                "folder to PYTHONPATH so `MvCameraControl_class` is importable)")


def _load_sdk():
    sdk = lazy_import("MvCameraControl_class", _IMPORT_HINT, purpose="control a HIKROBOT camera")
    params = lazy_import("CameraParams_header", _IMPORT_HINT, purpose="control a HIKROBOT camera")
    return sdk, params


class HikrobotCamera(Instrument):
    """A HIKROBOT/Hikvision MVS camera. Opens the `device_index`-th enumerated
    device (USB or GigE), forces Mono8 for deterministic intensity readout,
    and (optionally) sets exposure. Call `grab()` for a 2-D uint8 numpy frame.
    """

    def __init__(self, device_index=0, exposure_us=None, timeout_ms=1000):
        import ctypes
        self._ctypes = ctypes
        self._sdk, self._params = _load_sdk()
        MvCamera = self._sdk.MvCamera
        p = self._params

        device_list = p.MV_CC_DEVICE_INFO_LIST()
        layer_type = p.MV_GIGE_DEVICE | p.MV_USB_DEVICE
        ret = MvCamera.MV_CC_EnumDevices(layer_type, device_list)
        if ret != 0:
            raise RuntimeError(f"MV_CC_EnumDevices failed (0x{ret & 0xffffffff:08x})")
        if device_list.nDeviceNum == 0:
            raise RuntimeError("No HIKROBOT cameras found.")
        if not (0 <= device_index < device_list.nDeviceNum):
            raise ValueError(f"device_index {device_index} out of range "
                             f"(found {device_list.nDeviceNum} camera(s))")

        info = ctypes.cast(device_list.pDeviceInfo[device_index],
                           ctypes.POINTER(p.MV_CC_DEVICE_INFO)).contents
        self._cam = MvCamera()
        self._check(self._cam.MV_CC_CreateHandle(info), "MV_CC_CreateHandle")
        self._check(self._cam.MV_CC_OpenDevice(p.MV_ACCESS_Exclusive, 0), "MV_CC_OpenDevice")

        # Continuous, software-free acquisition; Mono8 so a frame maps
        # straight to a uint8 HxW array with no debayering/stride surprises.
        self._cam.MV_CC_SetEnumValue("TriggerMode", 0)
        try:
            self._cam.MV_CC_SetEnumValueByString("PixelFormat", "Mono8")
        except Exception:
            pass
        if exposure_us is not None:
            self.set_exposure_us(exposure_us)

        self._timeout_ms = timeout_ms
        self._check(self._cam.MV_CC_StartGrabbing(), "MV_CC_StartGrabbing")

    def _check(self, ret, what):
        if ret != 0:
            raise RuntimeError(f"{what} failed (0x{ret & 0xffffffff:08x})")

    def set_exposure_us(self, exposure_us):
        try:
            self._cam.MV_CC_SetEnumValue("ExposureAuto", 0)
        except Exception:
            pass
        self._check(self._cam.MV_CC_SetFloatValue("ExposureTime", float(exposure_us)),
                    "set ExposureTime")

    def set_gain(self, gain_db):
        try:
            self._cam.MV_CC_SetEnumValue("GainAuto", 0)
        except Exception:
            pass
        self._check(self._cam.MV_CC_SetFloatValue("Gain", float(gain_db)), "set Gain")

    def grab(self):
        """Grab one frame as a 2-D uint8 numpy array (height, width)."""
        ctypes = self._ctypes
        p = self._params
        frame_info = p.MV_FRAME_OUT_INFO_EX()
        ctypes.memset(ctypes.byref(frame_info), 0, ctypes.sizeof(frame_info))

        stParam = p.MVCC_INTVALUE()
        ctypes.memset(ctypes.byref(stParam), 0, ctypes.sizeof(stParam))
        self._check(self._cam.MV_CC_GetIntValue("PayloadSize", stParam), "get PayloadSize")
        payload = stParam.nCurValue
        buf = (ctypes.c_ubyte * payload)()

        self._check(self._cam.MV_CC_GetOneFrameTimeout(buf, payload, frame_info, self._timeout_ms),
                    "MV_CC_GetOneFrameTimeout")
        h, w = frame_info.nHeight, frame_info.nWidth
        return np.frombuffer(buf, dtype=np.uint8, count=w * h).reshape(h, w).copy()

    def measure_fn(self, roi=None, reducer="sum", frame_averages=1):
        """Return a `() -> float` for SLM.run_efficiency_calibration / sweeps:
        grabs a frame and reduces it to one number.

        roi: (x0, y0, x1, y1) pixel box to integrate over (default: whole
             frame) -- point it at the diffraction order you're measuring.
        reducer: "sum" (total counts, ~ optical power in the ROI) or "max"
             (peak pixel).
        frame_averages: average this many frames per call (noise reduction).
        """
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
        try:
            self._cam.MV_CC_StopGrabbing()
        except Exception:
            pass
        try:
            self._cam.MV_CC_CloseDevice()
        except Exception:
            pass
        try:
            self._cam.MV_CC_DestroyHandle()
        except Exception:
            pass
