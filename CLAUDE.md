# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

This folder holds both the original R&D prototype and the real software it's growing into: an SLM
(spatial light modulator) control application. Given target beam parameters, it generates a
phase-only hologram to shape a laser beam — currently vortex/OAM (Laguerre-Gaussian) beams, plus a
growing catalog of other phase structures (focusing, gratings, axicons, Zernike aberration
correction, hybrid/multiplexed combinations). `slm_toolbox/` is the Python phase-generator engine;
the Mathematica notebook and images below are the original physics reference/parity target, not the
shipping code.

## Commands

Pure Python + numpy/scipy/Pillow (+ tkinter stdlib for the GUI). **`slm_toolbox` is a real
installable SDK** (`pyproject.toml`, name `slm-toolbox`, v0.2.0): `pip install -e .` (or
`pip install -e ".[instruments,notebook,cv]"` / `".[all]"`) makes it importable from any project or
Jupyter kernel — **it is currently editable-installed into the user's Python 3.14**, so
`import slm_toolbox` works from any cwd (the standalone `examples/`/`tests/` scripts still also
`sys.path.insert` the repo root so they run without an install). `packages` in pyproject **must list
both `slm_toolbox` and `slm_toolbox.instruments`** (the subpackage was missing in v0.1.0). Optional
extras map to the lazy hardware deps (`instruments` = pyserial/pyvisa/thorlabs-elliptec, `cv` =
opencv-python, `notebook` = jupyter/ipython); the HIKROBOT MVS SDK is not pip-installable. If you add
a new top-level module or subpackage, update `pyproject.toml`'s `packages` and the top-level
`__init__.py` re-exports.

Regenerate the example galleries:

```bash
python examples/generate_fork_gallery.py      # vortex+grating forked holograms, L=-5..5
python examples/generate_pattern_gallery.py   # one example of every phase type + a hybrid combo
```

Output PNGs land in `examples/output/`.

**Jupyter**: `examples/quickstart.ipynb` is a runnable tour (built with `nbformat`; verified to
execute end-to-end via `nbconvert --execute` — 0 errors, inline images render). `slm_toolbox.notebook`
provides `show()` / `to_image()` / `far_field_image()` returning `PIL.Image` (Jupyter auto-renders a
returned PIL image inline; PIL-only, no matplotlib). These are re-exported at the top level
(`from slm_toolbox import show, far_field_image`).

**Docs are generated to PDF via a scratchpad `md_to_pdf.py`** (reportlab, Windows Arial/Consolas TTFs
registered for Greek/math glyphs; handles headings/code-fences/bullets/numbered-lists/**pipe tables**/
inline spans; emoji + `∝`-type glyphs not in Arial must be mapped to text or they drop). Persistent
outputs: `calibration_SOP.pdf`, `PROGRESS_REPORT.pdf`. The converter script itself is transient
(session scratchpad) — rewrite it from the `.md` if a PDF needs regenerating; verify with
`pypdf` text-extraction (no PDF renderer available in-env, so check extracted text + glyph coverage
against the font's cmap rather than eyeballing).

**Scripting API** (for automated optoelectronic measurements, no GUI involved):
`python examples/api_measurement_example.py` demonstrates it end-to-end (runs standalone with a fake
instrument reading, swap in a real one to use for real). See `slm_toolbox/api.py` below.
`python examples/instruments_measurement_example.py` is the fuller version — SLM + real lab
instruments (rotation mount + power meter + camera), running against mocks by default (flip
`USE_MOCK=False`). See `slm_toolbox/instruments/` below.

**Camera-feedback self-calibration** (no hardware to try it):
`python examples/self_calibration_example.py` — a closed SPGD loop corrects a hidden aberration
using only a (simulated) camera's image sharpness. See `slm_toolbox/feedback.py` +
`slm_toolbox/autocalibrate.py` below.

**Head-less regression tests** (no hardware, no GUI): `python tests/test_simulate.py`,
`python tests/test_instruments.py`, `python tests/test_autocalibrate.py` — plain `assert`+print
scripts (not pytest).

**Interactive GUI**: `run_gui.bat` (installs numpy/scipy/pillow via pip if missing, then launches
`phase_gui.py`). Windows-only entry point, mirrors the sibling AutoDraw-py project's `run.bat`
convention. `phase_gui.py` is a Tkinter app: a layer list + editor lets you add any number of
`slm_toolbox.patterns` phase types (vortex, grating, lens, axicon, LG mode, Zernike term,
checkerboard, random), each with its own params and a weight multiplier; all enabled layers are
summed via `compose.sum_phases`/`wrap_phase` (same additive-overlay model as the library) and
rendered live in a preview pane; "Save Pattern..." exports the full-resolution grayscale frame as
PNG/BMP. The preview pane itself is a downscaled thumbnail (quick glance only); **"View
Full-Resolution..."** opens an ordinary, resizable/scrollable window showing the pattern at its
true native resolution with no resampling, for pixel-perfect inspection on your own monitor without
needing the SLM connected — distinct from "Projection" below, which is for actually sending it to
the SLM. Starts pre-loaded with a vortex(l=3)+grating fork hologram. Global Width/Height default to
**1920x1080** (`slm_toolbox.display.DEFAULT_SLM_WIDTH/HEIGHT`) — the common resolution for an
HDMI-connected SLM acting as a secondary monitor.

**Center offset**: Global parameters has a "Center X,Y (px)" pair that shifts *every* layer's origin
together (e.g. to align the whole pattern with where the beam actually hits the SLM, if not exactly
centered); each layer additionally has its own "Center offset X,Y (px)" that adds on top of the
global value (e.g. to decenter one lens relative to an otherwise-centered vortex). Both are just the
`center=` kwarg every `patterns.*` function already accepted — the GUI/API previously never exposed
it. Implemented via `phase_gui.effective_center()`.

**Camera + self-calibration panel** (bottom of the GUI): a "Source" selector (**"Simulated (no
hardware)"** — a `SimFeedbackCamera` imaging the far-field of the current pattern, default so the
feature works with nothing plugged in; or **"HIKROBOT (MVS SDK)"** for the real camera), Connect /
Grab Frame (shows the frame + its sharpness/peak/saturation) / **"Self-Calibrate Aberration"**. Self-
Calibrate runs `autocalibrate.optimize_zernike` (SPGD on the camera sharpness metric) over the
Zernike terms in the box, on top of the *current* composed layers as the base, then **appends the
found correction as Zernike-Term layers** (so it persists and is editable) and reports the sharpness
gain. The simulated source injects a preset test aberration so the button visibly finds+cancels it
(recovers it near-exactly on a flat/focus base at ~100 iters; a vortex+grating fork base converges
less cleanly — calibrate system aberration on a simple focus). Drives the GUI through a tiny
`_GuiCalibrationSlm` adapter (shares `_last_phase` on the app so the camera images what the loop
displays; renders+updates the projector only if one is open — skipped for the simulated camera to
keep the loop fast; pumps `master.update()` each step so the window stays responsive — the loop runs
in the main thread, Tk isn't thread-safe). Note: `ImageTk.PhotoImage(..., master=self.master)` is
passed explicitly (Python 3.14 headless loses the default-root ref after many `update()` calls).

**Projection (send to SLM over HDMI)**: an HDMI-connected SLM enumerates to Windows as an ordinary
secondary display, so "projecting" is: enumerate monitors (`slm_toolbox/display.py`,
`ctypes`+`EnumDisplayMonitors`/`GetMonitorInfoW`, no extra dependency), open a borderless
always-on-top window pinned exactly over the target monitor's bounds (`display.ProjectorWindow`),
and show the rendered grayscale frame **at native resolution with no resampling** — resizing would
interpolate phase values and corrupt the hologram, so the GUI warns (and asks to confirm) if the
pattern's pixel size doesn't match the selected monitor's resolution. The GUI's "Projection" panel
auto-selects the first non-primary monitor as the guessed SLM target
(`display.default_slm_monitor`) and lets you pick a different one, project, or stop (Escape key on
the projector window also closes it). `main()` also positions the *control* window itself on the
non-SLM monitor at startup, so the GUI doesn't accidentally open on top of the SLM display.
Verified via direct Win32 introspection (`EnumWindows`/`GetClassName`/`GetWindowRect`, matching PID)
that the projector window is created with the exact correct class/size/position on the target
monitor; visually confirming the pattern actually paints the physical second screen (vs. a
same-machine screenshot artifact) should still be spot-checked on real hardware — screenshotting a
second monitor from an automated/background test process in this environment was unreliable enough
that it isn't full proof on its own.

## `slm_toolbox/` architecture

Additive-overlay composition, matching both the Mathematica prototype and surveyed vendor SLM
software (see the project memory `oam-slm-control-software` for the research this was based on):
generate each phase term separately (radians, unwrapped) → sum them → wrap to `[0, 2*pi)` → render to
a grayscale SLM frame → save.

- **`grid.py`** — pixel-unit and physical-unit (meters, via `pixel_pitch_m`) coordinate grids shared
  by every generator. Every generator except `random_phase` takes an optional `center=(cx, cy)`
  (pixel coords, defaults to the array's exact geometric center) — this is what the GUI's per-layer
  and global center-offset controls (below) drive.
- **`patterns.py`** — one function per phase structure: `vortex_phase` (OAM spiral phase),
  `blazed_grating_phase` (beam steering/order separation — tilts the light path by an arbitrary
  angle via grating period), `beam_position_phase` (the same physical tilt as
  `blazed_grating_phase`, but parameterized by *where you want the spot* — `(dx_m, dy_m)` at a given
  lens's focal plane — instead of grating period/angle; cross-checked to be numerically identical to
  the manually-derived grating equivalent, up to an irrelevant constant phase offset), `fresnel_lens_phase`
  (focus, converging or diverging), `axicon_phase` (Bessel beam if `sign=+1`, annular/ring beam if
  `sign=-1` — same physical hologram idea as `grating L=<n>_.jpg` but for focusing rings instead of a
  vortex fork), `lg_mode_field` (full complex LG_{p,l} field — same normalization/Gouy-phase
  convention as the notebook; returns amplitude+phase, take `np.angle(...)` for a phase-only mask),
  `zernike_phase` (aberration correction, `(n, m)` double-index coefficients), plus
  `checkerboard_phase`/`random_phase` (calibration/diffuser test patterns). **To move the spot /
  tilt the beam**: either `blazed_grating_phase` directly, or `beam_position_phase` + a
  `fresnel_lens_phase` at the same `focal_length_m` in the same composed pattern (see the GUI's
  "Beam Position (steer to X,Y)" layer type, or `SLM.steer_to(...)` in `api.py`). Validated against
  `simulate.py`: a lens alone focuses exactly on-axis; adding the steering term moves the simulated
  focus spot to within one far-field grid pixel of the predicted physical position.
- **`compose.py`** — `sum_phases(*phases)` (elementwise sum) and `wrap_phase` (mod 2π). This is the
  *only* combination method implemented — matches vendor "overlay" design; no interleaving/random
  spatial-multiplexing yet (that's a documented alternative in the survey, not built).
  `examples/generate_pattern_gallery.py`'s `hybrid_vortex_lens_grating` demonstrates composing three
  overlays (steer + focus + vortex) in one hologram.
- **`render.py`** — `phase_to_gray` maps wrapped phase onto the gray-level range; if a `gamma_lut` is
  given (see `calibration.py` below) it's used instead of a plain linear map. `save_pattern` writes
  8-bit (`'L'`) or 16-bit (`'I;16'`) images via Pillow.
- **`calibration.py`** — wavelength-dependent gray-level<->phase calibration. A phase-only LC-SLM
  doesn't take "phase" as input; the host sends a gray level, the panel's own driver converts that to
  a voltage, and the resulting phase retardation is nonlinear in gray level *and* depends on
  wavelength (phase retardation for a fixed voltage scales roughly as `1/wavelength`). `CalibrationCurve`
  holds a measured `(gray[], phase_rad[])` curve for one wavelength and inverts it into the
  `gamma_lut` array `render.phase_to_gray` expects; `CalibrationCurve.rescale_to_wavelength` gives an
  approximate curve at an uncalibrated wavelength via the `1/wavelength` relation (clearly labeled
  `source="rescaled-from-..."`, not a real measurement). `CalibrationLibrary` is a folder of saved
  per-wavelength JSON curves (`calibrations/<wavelength>nm.json`, gitignored/local-only — these are
  specific to one physical SLM panel) and resolves a requested wavelength to: an exact measured match
  → a rescaled nearest measurement (with a warning) → an explicit uncalibrated linear 0..2π fallback
  (`CalibrationCurve.linear_fallback`) if nothing is on file at all. **Deliberately ships with zero
  built-in calibration numbers** — fabricating plausible-looking calibration data would silently
  corrupt real hologram output, so the fallback is always clearly labeled as unmeasured. See
  `calibration_SOP.md` for how to actually measure a curve for your panel.
- **`calibration_patterns.py`** — raw gray-level test patterns for actually *measuring* a curve
  (bypasses the phase pipeline entirely, since gray level is the independent variable during
  calibration): `two_level_grating_pattern` (Method C base pattern) and
  `self_referenced_calibration_pattern` (Method A base pattern: grating half + uniform piston half).
  `calibration.efficiency_to_phase_diff`/`unwrap_efficiency_sweep` invert a Method C diffraction-
  efficiency sweep into a phase curve (validated against synthetic ground-truth data — accuracy
  limited by discrete sample density near the sweep's efficiency peak, and by noise sensitivity near
  the sweep's endpoints; both are inherent to the method, not fixable in software, and documented in
  the function docstring). `CalibrationCurve.from_efficiency_sweep` wraps this into a saveable curve.
- **GUI wiring** (`phase_gui.py`): the "Calibration" panel resolves+applies the right curve for the
  current Wavelength field automatically on every "Generate Preview" (so it also applies to
  Save/Project, which reuse the same rendered frame). Four ways to populate a calibration:
  **"Calibration Wizard (Method C)..."** is a full guided workflow — generates a gray-level sweep,
  projects the reference-vs-test grating for each level on the target monitor, takes your typed-in
  efficiency reading per level, and computes+saves the curve once complete (tested end-to-end
  headlessly with synthetic sin² efficiency data reproducing a known ground-truth curve). **"Self-
  Referenced Pattern (Method A)..."** projects the grating/piston pattern for a chosen piston gray
  level (phase extraction from the resulting fringes is setup-specific, not automated). **"Enter/Edit
  Calibration..."** pastes measured `gray,phase_rad` points directly. **"Load Calibration File..."**
  imports a previously-saved/exported JSON curve.
- **`api.py`** — `SLM`, the scripting entry point for automated optoelectronic measurements (no GUI):
  a context-manager class wrapping monitor selection, the phase generators (shape/wavelength
  pre-bound, e.g. `slm.vortex(l)`, `slm.grating(period_px)`), `render()`/`display_phase()`
  (calibration auto-applied per `slm.wavelength_nm`, reuses one projector window across calls via
  `ProjectorWindow.update_image` for fast sweeps rather than recreating it), and
  `run_efficiency_calibration(measure_fn)` — a **fully automated** Method C calibration loop that
  drives your own instrument-read callback (power meter/DAQ/etc.) through the gray-level sweep and
  computes+saves the curve, no manual data entry (the GUI wizard's steps, scripted). Manages its own
  hidden `tk.Tk()` root internally (`root.update()` pumped during `settle_s` waits) — the caller never
  touches Tkinter. See `examples/api_measurement_example.py`.
- **`simulate.py`** — predicts what a phase pattern will actually produce optically, via FFT
  (Fraunhofer far-field / focal-plane-of-a-lens diffraction), with **no hardware needed at all** —
  `simulate_far_field(phase_rad, wavelength_m, pixel_pitch_m, amplitude=None)` returns the predicted
  intensity pattern; `gaussian_illumination` gives a more realistic illumination envelope than the
  uniform default; `on_axis_intensity`/`radial_profile` characterize doughnut/ring shapes without
  eyeballing an image. This is also a genuine correctness check on the pattern generators, not just a
  preview: `tests/test_simulate.py` verifies hard physical facts (a vortex phase produces an *exact*
  on-axis intensity null — the topological phase singularity — and the doughnut ring radius grows
  monotonically with |l|). **Caveat worth knowing**: on a square pixel grid, that on-axis null is only
  exact for vortex charge `l` NOT divisible by 4 — the grid's own 4-fold rotational symmetry leaves a
  real nonzero residual when `l % 4 == 0` (confirmed empirically, documented in
  `simulate.on_axis_intensity`'s docstring). This isn't a simulator bug; it's genuine aperture-
  truncation physics that applies to any pixelated device, including a real SLM's active area — worth
  remembering if `l` is ever a free/tunable parameter in an experiment (e.g. avoid `l` a multiple of 4
  if beam purity at the exact center matters). See `examples/simulate_far_field_gallery.py` for a
  rendered preview gallery (vortex doughnut, axicon ring, focused spot, vortex+lens).
- **`instruments/`** — lab instrument drivers for automated measurements alongside the SLM.
  **Two hard rules** (both tested in `tests/test_instruments.py`): (1) every heavy/vendor dependency
  (`pyvisa`, `thorlabs_elliptec`, the HIKROBOT MVS SDK) is imported *lazily at connect-time*, not at
  module load, so `import slm_toolbox.instruments` works on any machine with just numpy+pyserial and
  gives a clear actionable `ImportError` only when you actually open that device; (2) every real
  driver has a same-API mock in `mock.py`, so a full measurement script runs against fakes with no
  hardware. Detector-type drivers expose `measure_fn(...) -> (() -> float)`, which is exactly what
  `api.SLM.run_efficiency_calibration(measure_fn=...)` and sweeps consume. Modules:
  `elliptec.py` (Thorlabs Elliptec via the `thorlabs_elliptec` package — the same lib the existing
  `instruments codes/` rotation driver uses; `ElliptecBus` models the ELLB bus-distributor / ELLC
  interface-board serial port, and `ELL14Rotation`/`ELL15Iris`/generic `ElliptecDevice` are the
  addressed devices sharing it by `device_id` — ELLB/ELLC are the transport, not separately
  "controlled"; **ELL15 semantics unverified** — not a datasheet-confirmed model, flagged in its
  docstring), `power_meter.py` (`PM100` over pyvisa/SCPI — one class covers PM100/PM100D/PM100USB/
  PM160/PM400 since they share the SCPI command set; the existing folder used pylablib's PM160 class
  instead), `camera.py` (`HikrobotCamera` via the MVS SDK — **written to the standard MVS sample flow
  but NOT bench-tested**, no HIKROBOT driver existed in `instruments codes/` to reuse; needs
  first-connection validation, esp. pixel-format/stride). `base.py` has the `Instrument`
  context-manager base + `lazy_import` helper. Per-device method names (`get_power`, `move_absolute`,
  `home`, `close`) match the existing lab drivers' conventions. `mock.py` also has
  **`SimFeedbackCamera`** — a "camera" whose frames are the *simulated far-field* (`simulate.py`) of
  the SLM's currently-displayed phase, optionally plus a hidden Zernike aberration; it makes the
  closed feedback loop below fully testable/demonstrable with no hardware (it downsamples the SLM
  phase to a small square pupil for a fast FFT — crops the centered `min(h,w)` square first so a
  non-square panel isn't anisotropically distorted; real hardware has no such downsample).
- **`feedback.py`** + **`autocalibrate.py`** — camera-in-the-loop self-calibration (sensorless
  adaptive optics). `feedback.py` reduces a camera frame to scalar metrics (`sharpness` =
  Σ I²/(Σ I)², the standard AO metric to maximize; `find_spot` centroid/width via image moments;
  `auto_roi` to locate a diffraction order; `saturation_fraction` to reject clipped frames;
  `total_intensity` for a Method-C efficiency readout) — **pure numpy/scipy; OpenCV is optional**
  (only `auto_roi(use_cv2=True)` uses `cv2.connectedComponents`, lazily, with a numpy fallback).
  `autocalibrate.py` runs **SPGD** (Stochastic Parallel Gradient Descent) to maximize a camera
  metric: `optimize_zernike(slm, measure_metric, terms, ...)` finds the Zernike correction that
  cancels the system's aberration for the current wavelength (precomputes the per-term basis once —
  each SPGD step is then a cheap weighted sum, not a full-panel polynomial recompute), and
  `optimize_scalar` for auto-focus / auto-align. **Uses the NORMALIZED SPGD update** (step ∝
  (J⁺−J⁻)/(|J⁺|+|J⁻|)) so the gain is scale-invariant in the metric — the un-normalized form
  under-converged badly when the sharpness metric's absolute values were ~0.03 (see
  `spgd(..., normalize=...)`). Proven end-to-end in `tests/test_autocalibrate.py` and
  `examples/self_calibration_example.py`: inject a hidden aberration → the loop recovers the exact
  negated correction (to ~0.1 rad) and multiplies image sharpness ~3–4.5×. `api.SLM.render` now also
  stashes `_last_phase` (the wrapped phase last rendered) for `SimFeedbackCamera`/feedback loops.
- **`tests/`** — head-less regression scripts (not pytest, plain `assert`+print, matching the sibling
  AutoDraw-py project's convention): `test_simulate.py` (far-field physics) and `test_instruments.py`
  (driver imports/errors + mocks + SLM-calibration integration). Run each via `python tests/<file>`.
- **Parity check**: `generate_fork_gallery.py`'s output (512x512, `period_px=12`) visually matches the
  existing `grating L=<n>_.jpg` reference images fringe-for-fringe — use this as the regression check
  if you touch `vortex_phase` or `blazed_grating_phase`.

**Not yet built**: no *measured* calibration data (the machinery is built and tested with synthetic
curves, but `calibrations/` is empty until someone runs the SOP on real hardware), no Airy-beam or
vector-vortex generators, no multi-monitor persistence (projection target must be re-picked each GUI
session). "Projection" (above) is the hardware-output path now — it's a display window, not an SDK
integration, which is sufficient since the SLM is just an HDMI monitor. See the project memory for
the toolbox/SDK survey (e.g. `slmsuite`) if a vendor SDK integration (e.g. for hardware-triggered
frame sync) is needed later.

## `instruments codes/` — existing lab instrument drivers (not yet integrated)

A large (175-file) pre-existing collection of lab-automation code the user copied in, **not yet
integrated with `slm_toolbox`** — surveyed at a structural level only (2026-07-16), not deeply read.
Mostly Python + [pylablib](https://pylablib.readthedocs.io/), organized as `D110_project/instruments/`
(individual driver classes) + `D110_project/controllers/` (higher-level compositions) + `D110_project/
processing/`, plus a separate `4200 codes/` sub-project (Keithley 4200 parameter analyzer) and
`Python_Sample_EN/` (uncurated vendor sample scripts). 48 Jupyter notebooks are the primary
"documentation" (ad-hoc, no README). No test suite.

**Confirmed (2026-07-16, actual driver code read)**: their Elliptec driver uses the
**`thorlabs_elliptec`** PyPI package (`ELLx(x=14, serial_port="COM4", device_id=1)`; multi-drop by
chaining a shared serial connection across `device_id`s — no ELLB/ELLC objects, the interface board
is just the COM port); their power meter uses **pylablib's `PM160`** over a VISA resource string
(`get_power()` → watts, `set_wavelength(meters)`); there is **no HIKROBOT/camera driver** (only an
Andor SDK2 camera in `spectrometer.py`); **no ELL15/iris** driver. The **HOLOEYE SLM driver
(`slm.py`) uses the real HEDS Python SDK v4.x** (`import HEDS`, `HEDS.SLM.Init`,
`showVortex(l, centerX, centerY)`, `showBlank`) — confirming real HOLOEYE vendor-SDK hardware access
exists, a genuinely different route than `slm_toolbox/display.py`'s HDMI-monitor approach. (Also: a
pre-existing syntax error in `controllers/power_control.py` L16 — `if unit is not None` missing its
colon.)

**What was built from this** (2026-07-16): a NEW clean driver layer at `slm_toolbox/instruments/`
(documented above) for the devices the user asked for — Elliptec ELL14/ELL15 + ELLB/ELLC bus, PM100
power meter, HIKROBOT camera — based on the APIs confirmed here, but **not** modifying anything inside
`instruments codes/` (still treated as read-only source). The `thorlabs_elliptec` package choice and
the PM VISA/get_power()→watts convention were copied from their working code.

**Still not done**: the HEDS-SDK SLM path is NOT integrated (still a separate deferred pass — see
`instruments_integration_prompt.md` and the project memory); their controllers (polarization/OAM
scans) aren't wired in; the other instruments (Andor spectrograph, NI-DAQ, Keithley 4200, lock-in,
etc.) have no `slm_toolbox` drivers yet.

## Contents

- **`LG modes _ grating and phase for SLM (1).nb`** — Mathematica notebook (requires Wolfram
  Mathematica/Player to open; ~16 MB, almost entirely embedded/cached `DensityPlot` graphics, so
  don't try to read it as text — grep for cell input code instead of paging through it). It defines
  the complex field of a Laguerre-Gaussian (LG) beam and renders `|field|^2` intensity maps. Key
  quantities in the notebook, useful if porting this math to real code:
  - Beam/physical params: `λ` (wavelength, hardcoded 1064 nm), `ω₀` (waist, 40 µm), Rayleigh range
    `zR = π ω₀² / λ`, beam radius `ωz`, Gouy phase `θG = ArcTan(zR, z)`.
  - LG mode amplitude `A`: standard normalized LG_{p,l} form — radial part via `LaguerreL[p, |l|, ...]`,
    Gaussian envelope, azimuthal vortex phase `l·φ`, and the Gouy term `(2p+|l|+1)·θG`.
  - `Ψ1`/`W1`: a weighted **superposition of LG modes** over an index `k = 0..M` (binomial-style
    weights, each term with its own OAM index `l = lo + v·k` and radial index `p = po + u·k`) — i.e.
    the notebook already supports generating **mode superpositions**, not just a single pure vortex.
  - Rendered via `DensityPlot[Abs[W1]^2, ...]` with `PlotPoints -> 101`, fixed frame size scaled by
    `√(p+|l|+2) · 3.5 · ωz`.
- **`grating L=<n>_.jpg`** (n = -5..5) — rendered **forked diffraction gratings**: a blazed linear
  grating (spatial carrier, for 1st-order beam separation on the SLM) summed with the azimuthal
  vortex phase, phase-wrapped and shown as a binary fringe pattern. The fork dislocation count at
  center equals `|L|`; this is the classic "vortex + grating → fork hologram" encoding used to
  generate OAM beams from an SLM's diffracted order. `L=0` is a plain unforked grating (control case,
  no OAM).
- **`OAM0.bmp` … `OAM5.bmp`, `OAM-1.bmp` … `OAM-5.bmp`** — companion raw bitmap renders (paired with
  the grating jpgs by topological charge index) — check these as reference images/masks when
  building an actual phase-map generator, since they represent the target hologram raster the SLM
  would receive.
- **`OAM.pptx`** — slide deck summarizing this work (background/results); consult it for the
  narrative/context around the notebook if picking this project up.
- **`calibration_SOP.md`** (+ a generated `calibration_SOP.pdf` printable copy — regenerate via the
  one-off `md_to_pdf.py`-style script if the .md changes; not checked in as a build step, just a
  convenience snapshot) — how to measure a real gray-level<->phase curve for your specific SLM panel
  at a specific wavelength (interferometric and non-interferometric methods, sampling guidance,
  common pitfalls), and how to load the result via the GUI's Calibration panel/wizard. Read this
  before trusting any pattern sent to real hardware — see `slm_toolbox/calibration.py` above for why.

## Working in this folder

- Treat the notebook's formulas as the reference implementation when adding/changing
  `slm_toolbox` generators — validate new phase-generation code against them (e.g. compare a
  Python-rendered hologram to the corresponding `grating L=<n>_.jpg`/`OAM<n>.bmp` pair).
- Next steps beyond the current phase-generator engine + GUI + projection: Airy-beam and
  vector-vortex generators, a real per-device calibration LUT, remembering the last-used monitor
  selection, and (only if a vendor SDK's extra features are needed) real HOLOEYE/Meadowlark/
  Hamamatsu SDK integration instead of the generic HDMI-secondary-monitor approach.
