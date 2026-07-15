# SLM gray-level → phase calibration SOP

Why this exists, how to measure it for your panel and wavelength, and how to load the result into
`slm_toolbox`. See [`slm_toolbox/calibration.py`](slm_toolbox/calibration.py) (curve fitting/storage)
and [`slm_toolbox/calibration_patterns.py`](slm_toolbox/calibration_patterns.py) (the raw test
patterns to display) for the code this feeds, and the "Calibration" panel in `phase_gui.py` for the
UI — including a guided wizard for Method C below.

## 1. Why calibration is wavelength-dependent

A phase-only LC-SLM doesn't take "phase" as input — you send an 8-bit (or 16-bit) **gray level**
per pixel. The panel's own driver converts that gray level to a voltage, which sets the liquid
crystal's birefringence `Δn(V)`, which sets the phase retardation:

```
δ = 2π · d · Δn(V) / λ
```

(`d` = LC cell thickness, `λ` = wavelength — standard birefringent-retarder physics.) For a fixed
gray level (fixed voltage, fixed `Δn`), the resulting phase shift is inversely proportional to
wavelength: **the same 8-bit value gives you less phase shift at longer wavelengths.** In practice
`Δn` itself also has some wavelength dispersion, so it's not *exactly* `1/λ`, but `1/λ` is the
dominant, first-order effect — real datasheet numbers show the trend clearly on a single device,
e.g. HOLOEYE's PLUTO-2.1-VIS-016 panel: **6.9π at 530nm vs. 5.2π at 633nm**, same panel, same drive
range [holoeye.com/slm-pluto-phase-only]. This means a panel calibrated (gray 0-255 spans exactly
0-2π) at one wavelength will **not** span exactly 0-2π at another wavelength — it might only reach
1.5π, or it might wrap past 2π and become ambiguous. **Calibration must be redone (or at least
re-verified) per wavelength.**

## 2. How HOLOEYE's own software handles this (for reference)

HOLOEYE's SLM Pattern Generator software's phase→gray-level algorithm explicitly **assumes the
panel is already calibrated so that gray 0-255 spans exactly 2.0π rad**
[holoeye.com/products/spatial-light-modulators/slm-pattern-generator/] — the pattern-generation
software itself does not adapt to wavelength; the calibration is applied at the **device** level.
HOLOEYE panels (PLUTO-2.1, LUNA, LETO-3, GAEA-2.1, ERIS-1.1, GAEA-C) ship with a separate
**Configuration Manager** utility that uploads "a new gamma curve or another digital drive scheme"
onto the SLM controller itself via USB/virtual COM port [consistent across all listed HOLOEYE
product pages]. In other words: HOLOEYE's answer to "different wavelength → different gamma" is
*swap the gamma curve loaded onto the device*, done once per working wavelength via their vendor
utility, after which the pattern-generation software's linear 0-2π assumption is valid again.

**We don't have that path** — an HDMI-connected SLM has no vendor firmware access from a generic
host; there's no equivalent to HOLOEYE's Configuration Manager here. `slm_toolbox` gets the same
end result a different way: instead of correcting the *device*, `calibration.py` corrects the
*gray value we send* (the `gamma_lut` passed into `render.phase_to_gray`), computed host-side from
a measured curve for the current wavelength. Functionally equivalent output, done in software
instead of firmware.

## 3. Measurement methods

Three practical options, roughly in order of rigor vs. equipment needed:

### Method A — Common-path / self-referenced interferometry (no external interferometer needed, most rigorous)

**The base pattern is wired up in the GUI**: Calibration panel → **"Self-Referenced Pattern (Method
A)..."** projects the grating-half/piston-half pattern below for whatever piston gray level you set
— phase extraction from the resulting fringes is setup-specific (depends on your camera/optics), so
that part isn't automated; once you have gray→phase points from your own fringe analysis, enter
them via "Enter/Edit Calibration...".

Based on Martínez Fuentes et al., *"Interferometric method for phase calibration in liquid crystal
spatial light modulators using a self-generated diffraction-grating,"* Opt. Express 24(13):14159
(2016) — peer-reviewed, confirmed method:

- Split the SLM into two regions: one half displays a **binary diffraction grating**, the other
  half a **uniform gray level** (piston). The grating half diffracts light into a tilted plane
  wave; the piston half passes an undiffracted reference wave. These interfere directly —
  **no separate interferometer arm, beamsplitter, or reference mirror needed**; the SLM itself
  generates both waves. "Experimentally straightforward, robust, requires solely a collimated
  beam" [Opt. Express 24, 14159].
- Step the piston region's gray level through your full range (see §4 for sampling); a camera
  downstream of a small aperture/lens records the interference fringe pattern at each step. The
  measured fringe *phase* shift versus piston gray level **is** your gray→phase curve.
- This is the recommended method if you have a collimated beam and a camera but no dedicated
  interferometer optics.

### Method B — Twyman-Green interferometry, SLM-driven phase stepping (most efficient, needs interferometer optics)

Based on Lee, Koo & Kim, *"Simple and fast calibration method for phase-only spatial light
modulators,"* Opt. Lett. 48(1):5-8 (2023) — peer-reviewed, confirmed method:

- Standard Twyman-Green interferometer, but instead of physically stepping a piezo-driven mirror
  to phase-shift the reference arm (conventional N-step phase-shifting interferometry), **the SLM's
  own gray level modulates the interference intensity directly** — no PZT needed.
- Notably **faster**: "requires N times fewer interferograms than typical N-step phase-shift
  interferometry" [Opt. Lett. 48, 5], and can simultaneously extract **per-pixel** phase-response
  nonuniformity and panel flatness nonuniformity, not just a single global curve — worth using if
  you already have interferometer optics on the bench and want a per-pixel-accurate map instead of
  one global curve.

### Method C — Diffraction-efficiency-vs-gray-level (simplest, least equipment)

**This method is fully wired up in the GUI**: `phase_gui.py`'s Calibration panel → **"Calibration
Wizard (Method C)..."** steps you through it — pick a target monitor, it displays the reference-vs-
test grating for each gray level, you type in the measured efficiency, and it computes + saves the
calibration curve automatically once every level has a reading (via
`slm_toolbox.calibration.unwrap_efficiency_sweep` — validated against synthetic ground-truth data,
error shrinks with denser sampling as expected for this method). The practical fallback with just a
laser, the SLM, and a power meter (or camera) — no interferometer at all:

1. Display a **two-level binary phase grating** on the SLM: half the pixels (e.g. alternating
   columns) at a fixed reference gray level `g_ref` (commonly 0), the other half at a **test** gray
   level `g_test`.
2. Measure the **1st-order diffraction efficiency** (power in the ±1 diffracted order relative to
   incident power) as `g_test` is swept from 0 to 255.
3. For a binary phase grating, 1st-order efficiency is proportional to `sin²(Δφ/2)` where `Δφ` is the
   phase difference between the two gray levels — efficiency is **zero when `Δφ = 0` or `2π`** and
   **maximum when `Δφ = π`**. Sweeping `g_test` and finding the efficiency minima/maximum gives you
   `Δφ(g_test)` directly (invert the `sin²` relation), without needing to measure phase directly.
4. This is qualitatively less precise than A/B (no interferometric phase readout, and the `sin²`
   inversion is ambiguous in sign/branch without extra care), but it's the right choice if you have
   no way to build an interference setup at all — it directly reuses the "grating diffraction
   efficiency" physics already in this project's forked-hologram work.

## 4. Concrete procedure (applies to all three methods)

1. **Sample enough gray levels.** At minimum ~16-17 evenly spaced points across 0-255 (steps of
   16); 33 points (steps of 8) is a safer default if your panel might be non-monotonic or have a
   flat (saturated) region near the ends. Always include the endpoints 0 and 255.
2. **Let the panel settle** before each measurement — LC response has a settling time (ms-scale)
   and **panel heating drifts the calibration slowly over the session**; if you're doing a careful
   measurement, re-check a couple of reference points at the end and confirm they haven't drifted.
3. **Watch for flicker.** Many LC-SLMs use an AC drive scheme with a flicker component; average
   over multiple frames per gray level rather than a single snapshot to avoid aliasing it into your
   phase measurement.
4. **Watch for non-monotonicity and saturation.** Real panels often flatten out (phase stops
   increasing with gray level) near gray=0 and gray=max as the LC director hits its physical
   extremes. `CalibrationCurve.to_gamma_lut` in this codebase already handles flat/non-increasing
   regions defensively (nudges them to be strictly increasing before inverting), but it's still
   best practice to identify and note where your panel saturates and avoid relying on that region.
5. **Confirm total span.** After measuring, check whether your curve's phase actually reaches
   `2π` within gray 0-255. If it falls short (e.g. only 1.5π), gray 255 alone can't give you a full
   2π wrap — you're limited to whatever phase range you actually measured, which matters for
   patterns needing the full range (e.g. blazed gratings need a clean 2π sawtooth for high
   diffraction efficiency).
6. **Record wavelength precisely.** The whole point of this SOP is that the curve is only valid at
   the wavelength you measured it at (§1) — always label your saved calibration with the exact
   `λ` used.

## 5. Loading the result into `slm_toolbox`

Three ways, all in `phase_gui.py`'s "Calibration" panel:

- **"Calibration Wizard (Method C)..."** — computes and saves it for you as you go (§3, Method C) —
  the recommended path if you don't have interferometer optics.
- **"Enter/Edit Calibration..."** — paste your measured points as `gray,phase_rad` pairs (one per
  line) for the wavelength currently set in the Wavelength field, then Save. Use this for Method A/B
  results (phase from your own fringe analysis) or any other source. This writes
  `calibrations/<wavelength>nm.json`.
- **"Load Calibration File..."** — import a previously exported/saved JSON curve (same format —
  see `CalibrationCurve.to_dict`/`from_dict` in `slm_toolbox/calibration.py`).

Once saved, the GUI automatically resolves and applies the right curve whenever you Generate
Preview / Save / Project, based on the Wavelength field:

- **Exact match** (within ±2nm of a saved calibration) → uses it directly.
- **No exact match, but another wavelength is calibrated** → approximates via the `1/λ` relation
  (`CalibrationCurve.rescale_to_wavelength`) and clearly labels the result as approximate. Treat
  this as a starting point, not a substitute for measuring at your actual working wavelength —
  §1's real HOLOEYE datasheet numbers show the scaling isn't perfectly `1/λ` in practice (different
  LC mixtures have their own birefringence dispersion), so the further your working wavelength is
  from the measured one, the less accurate the rescale will be.
- **Nothing calibrated at all** → falls back to an explicit, clearly-labeled **uncalibrated linear**
  mapping (gray 0-255 → phase 0-2π directly). This is almost certainly wrong on real hardware —
  it exists only so the software has *something* to render before you've calibrated, never as a
  claim of correctness.

## Sources

- Physics: `δ = 2π·d·Δn/λ`, standard LC birefringent-retarder phase retardation (textbook LC optics).
- HOLOEYE phase-depth-vs-wavelength datasheet figures: [holoeye.com/slm-pluto-phase-only/](https://holoeye.com/slm-pluto-phase-only/),
  [holoeye.com/luna-phase-only-spatial-light-modulator/](https://holoeye.com/luna-phase-only-spatial-light-modulator/).
- HOLOEYE Configuration Manager / gamma-curve-per-device architecture: consistent across HOLOEYE
  PLUTO-2.1, LUNA, LETO-3, GAEA-2.1, ERIS-1.1, GAEA-C product pages
  ([holoeye.com/products/spatial-light-modulators/](https://holoeye.com/products/spatial-light-modulators/)).
- HOLOEYE SLM Pattern Generator's linear 0-2π assumption: [holoeye.com/products/spatial-light-modulators/slm-pattern-generator/](https://holoeye.com/products/spatial-light-modulators/slm-pattern-generator/).
- Method A: Martínez Fuentes, Fernández, Prieto, Artal, "Interferometric method for phase
  calibration in liquid crystal spatial light modulators using a self-generated diffraction-grating,"
  *Optics Express* 24(13):14159–14171 (2016).
- Method B: Lee, Koo & Kim, "Simple and fast calibration method for phase-only spatial light
  modulators," *Optics Letters* 48(1):5–8 (2023).
- Background review: "Progress in Phase Calibration for Liquid Crystal Spatial Light Modulators,"
  *Applied Sciences* 9(10):2012 (2019) — covers both interferometric and diffractive/self-generated
  calibration method families.

**Caveats (from adversarial fact-checking during research for this doc):** cross-device
comparisons of phase depth vs. wavelength (comparing *different* SLM product variants at different
wavelengths) were found to overstate how cleanly `1/λ` scaling holds, since different variants use
different LC mixtures each optimized for their band — the same-device datapoints cited above
(e.g. PLUTO-2.1-VIS-016 at two wavelengths) are more trustworthy evidence of the trend than
cross-model comparisons. One secondary source disagreed with HOLOEYE's own LUNA-TELCO-115 spec
(2.6π vs. 2.3π at 1550nm) — treat exact datasheet numbers as illustrative, not as a substitute for
measuring your specific panel.
