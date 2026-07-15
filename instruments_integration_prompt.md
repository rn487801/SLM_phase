Prompt for a dedicated session/task to integrate `instruments codes/` with `slm_toolbox`
(paste this as-is into a new Claude Code session, or use it as the prompt for spawn_task /
Agent). Written 2026-07-16 after a structural-only survey — nothing in `instruments codes/`
has been read in depth yet, so treat every specific claim below as a lead to verify, not a
established fact.

---

I'm working in `C:\Users\Nanyte\Desktop\OAM phase\`, which has two things that need to be
connected:

1. **`slm_toolbox/`** — a Python phase-generator + display engine for a spatial light modulator
   (SLM), fully documented in this folder's `CLAUDE.md` (read that first). The relevant piece
   here is `slm_toolbox/api.py`'s `SLM` class — specifically
   `SLM.run_efficiency_calibration(measure_fn, ...)`, which drives a gray-level sweep and calls
   `measure_fn() -> float` at each step to get a diffraction-efficiency reading, then computes
   and saves a phase calibration curve (`calibration_SOP.md` has the physics/procedure). Right
   now `measure_fn` has to be hand-written by whoever calls it — there's no real instrument
   wired in.

2. **`instruments codes/`** — a large (~175 file), pre-existing, uncurated collection of lab
   instrument-control code the user copied in from prior work. A structural survey (not a deep
   read) found: mostly Python using the `pylablib` library, organized as
   `D110_project/instruments/` (individual driver classes), `D110_project/controllers/`
   (higher-level compositions), `D110_project/processing/`, a separate `4200 codes/` subfolder
   (Keithley 4200), and `Python_Sample_EN/` (uncurated vendor samples). 48 Jupyter notebooks are
   the only "documentation" that exists (no README). Driver classes reportedly follow a
   consistent `__init__(resource_id)` / `get_<x>()` / `set_<x>()` / `close()` pattern.

   Instruments the survey *thinks* it found (verify each — filenames/notebook-name-based, not
   confirmed by reading the actual code): a Thorlabs PM160 power meter with a `get_power()`
   method, Thorlabs MFF flip mount, Thorlabs ELL14/ELL18 rotation stages, an Andor Shamrock
   spectrograph + SDK2 camera, NI-DAQmx USB-6501 digital I/O, GPIB instruments (possibly incl. an
   SR830 lock-in), a Keithley 4200 parameter analyzer, an ITECH IT6500 power supply, a Kinesis
   KBD101 stepper controller — and, importantly, **what looks like an existing HOLOEYE SLM driver**
   (`SLMController.set_OAM(l, x, y)`, referenced from a "SLM control test.ipynb").

## What I need you to do

1. **Read the actual instrument driver code**, not just filenames — start with
   `D110_project/instruments/` and the controllers that use them. Confirm or correct every claim
   in the "instruments the survey thinks it found" list above.

2. **Resolve the HOLOEYE SLM driver question first, before anything else** — this could change
   `slm_toolbox`'s whole hardware-output architecture. Find that driver, read it, and answer: does
   it talk to a real HOLOEYE SDK (meaning there might be actual HOLOEYE hardware / vendor SDK
   access available, which `slm_toolbox/display.py`'s generic "HDMI secondary monitor" approach
   currently assumes does NOT exist)? If a real HOLOEYE SDK path is viable, tell me clearly —
   don't just silently build around it — since it may be a better (or complementary) integration
   route than the current `ProjectorWindow` approach, and I'd want to decide deliberately whether
   to add it as an alternative backend.

3. **Build a real adapter for at least the power meter** into
   `slm_toolbox.api.SLM.run_efficiency_calibration`'s `measure_fn` signature (`() -> float`) —
   e.g. a new `slm_toolbox/instruments_adapters.py` with something like
   `power_meter_measure_fn(pm_instance) -> callable`. Base this on the actual driver API you find,
   not on the guessed `get_power()` name above. If other instruments (rotation stages for
   polarization scans, etc.) look like they'd combine usefully with `slm_toolbox`'s vortex/OAM
   sweeps (the existing controllers already do "OAM scan" / "polarization scan" work — read those
   notebooks to understand the intended experiment), propose wiring those in too, but don't guess
   — confirm the actual API first.

4. **Handle the no-hardware-connected case gracefully** — importing `pylablib` or vendor SDK
   bindings will likely fail or hang on a machine without the instrument physically attached
   (there is currently no SLM or other instrument connected for testing). Design/test any new code
   so it degrades cleanly (clear ImportError/connection-error messages) rather than crashing
   unhelpfully, and use mocked/fake instrument objects for any automated tests, following the
   pattern already used in `examples/api_measurement_example.py` (fake power meter) and the
   synthetic-ground-truth testing style used throughout `slm_toolbox` (see `tests/test_simulate.py`
   and the docstring notes in `slm_toolbox/calibration.py` for the pattern: validate math/wiring
   against known synthetic data since real hardware isn't available to test against).

5. **Don't touch anything in `instruments codes/`** unless asked — treat it as read-only source
   material to understand and wrap, not to refactor, until we've discussed what (if anything)
   should change there. It's messy (no tests, ad-hoc notebooks, hardcoded COM ports in vendor
   sample scripts) but it's the user's real working lab code.

6. Update this project's `CLAUDE.md` (the "`instruments codes/`" section already has a stub —
   replace the "not yet integrated" framing with what's actually true once you've done this) and
   the project memory (if you have memory tools available) with what you found and built.

Given the folder's size, use Explore/general-purpose agents liberally to survey before reading
files in full — avoid blowing up your own context reading 175 files serially.
