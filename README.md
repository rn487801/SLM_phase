# slm-toolbox

A Python SDK for **spatial light modulator (SLM)** control: phase-pattern generation, HDMI
projection, per-wavelength gray↔phase calibration, automated optoelectronic measurement, and
camera-feedback self-calibration. Importable from any Python project or Jupyter notebook.

The core imports with just numpy / scipy / pillow — every hardware/vendor dependency (VISA power
meters, Elliptec stages, the HIKROBOT camera SDK, OpenCV) is **optional and lazily imported**, so the
package works on a machine with no instruments attached.

## Install

From the project folder (editable install — recommended so a Jupyter kernel anywhere picks it up):

```bash
pip install -e .
# with optional hardware/notebook extras:
pip install -e ".[instruments,notebook,cv]"     # or ".[all]"
```

The HIKROBOT camera additionally needs the vendor **MVS SDK** (not pip-installable) on `PYTHONPATH`.

## Quickstart (Jupyter)

```python
import slm_toolbox as slm
from slm_toolbox import patterns, compose, show, far_field_image

shape = (512, 512)

# A forked vortex hologram (OAM charge l=3 + a blazed grating), displayed inline:
phase = compose.sum_phases(
    patterns.vortex_phase(shape, l=3),
    patterns.blazed_grating_phase(shape, period_px=12),
)
show(phase)                                  # inline grayscale hologram

# Predict the actual beam it produces (a doughnut), no hardware:
far_field_image(patterns.vortex_phase(shape, l=3), wavelength_m=1064e-9, pixel_pitch_m=8e-6)
```

`show(...)` and `far_field_image(...)` return `PIL.Image` objects, which Jupyter renders inline when
they're the last expression in a cell.

## Driving a real (or mock) SLM

```python
from slm_toolbox import SLM

with SLM(wavelength_nm=1064) as s:            # picks the SLM's HDMI monitor
    s.display_phase(s.vortex(3), s.grating(period_px=12))   # project a fork hologram
    # automated Method-C calibration against any instrument read callback:
    # s.run_efficiency_calibration(measure_fn=my_power_meter.read)
```

Develop measurement scripts with **no hardware** using the mocks:

```python
from slm_toolbox.instruments import mock
pm  = mock.MockPM100(wavelength_nm=1064)      # same API as the real PM100
cam = mock.MockHikrobotCamera()               # same API as HikrobotCamera
```

## What's in the box

| Area | Module |
|---|---|
| Phase generators (vortex, grating, lens, axicon, LG, Zernike, beam-steer) | `slm_toolbox.patterns` |
| Compose + render + save | `compose`, `render` |
| HDMI projection | `display` |
| Per-wavelength calibration | `calibration`, `calibration_patterns` |
| Far-field beam simulation | `simulate` |
| Camera image metrics + SPGD self-calibration | `feedback`, `autocalibrate` |
| Scripting API for automated measurement | `api` (`SLM`) |
| Instrument drivers (Elliptec, PM100, HIKROBOT) + mocks | `instruments` |
| Jupyter inline display | `notebook` (`show`, `to_image`, `far_field_image`) |
| Interactive GUI (Windows) | `phase_gui.py` / `run_gui.bat` |

See `PROGRESS_REPORT.md` for status, `calibration_SOP.md` for the calibration procedure, and
`examples/` for runnable demos (all standalone, no hardware).

## Testing

```bash
python tests/test_simulate.py
python tests/test_instruments.py
python tests/test_autocalibrate.py
```
