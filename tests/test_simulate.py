"""Head-less physics regression checks for slm_toolbox.simulate -- no
hardware, no GUI. These are hard physical facts (a vortex phase MUST
diffract to exact zero intensity on-axis; the doughnut ring radius MUST
grow monotonically with |l|), not fuzzy approximations, so they're a
genuine correctness check on the pattern generators + simulator together.

Run: python tests/test_simulate.py  (exits nonzero on failure)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slm_toolbox import patterns, simulate

SHAPE = (256, 256)
WAVELENGTH_M = 1064e-9
PIXEL_PITCH_M = 8e-6

failures = []


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        failures.append(name)


def main():
    flat = np.zeros(SHAPE)
    intensity_flat, _ = simulate.simulate_far_field(flat, WAVELENGTH_M, PIXEL_PITCH_M)
    check("flat phase: on-axis intensity is the far-field peak (== 1.0)",
          abs(simulate.on_axis_intensity(intensity_flat) - 1.0) < 1e-9)

    # l values NOT divisible by 4: the on-axis null should be essentially
    # exact (machine precision). l divisible by 4 is deliberately excluded --
    # a square pixel grid has exact 4-fold (C4) rotational symmetry, which
    # (confirmed empirically) leaves a real, nonzero on-axis residual
    # specifically when l % 4 == 0 (the grid's own discrete symmetry order
    # divides evenly into the vortex winding number). This isn't a simulator
    # bug -- it reflects genuine aperture-truncation physics that applies to
    # any pixelated device, including a real SLM's rectangular active area,
    # not just this simulation.
    ring_radii = []
    for l in [1, 2, 3, 5, 6, 7, 9, 10]:
        vphase = patterns.vortex_phase(SHAPE, l=l)
        intensity_v, _ = simulate.simulate_far_field(vphase, WAVELENGTH_M, PIXEL_PITCH_M)
        on_axis = simulate.on_axis_intensity(intensity_v)
        check(f"vortex l={l}: exact on-axis null (phase singularity)", on_axis < 1e-20)

        radii, profile = simulate.radial_profile(intensity_v)
        ring_radii.append(radii[int(np.argmax(profile))])

    check("vortex doughnut ring radius grows monotonically with |l|",
          all(b > a for a, b in zip(ring_radii, ring_radii[1:])))

    # l=0 (a "vortex" with zero charge) must reduce to the flat-phase case --
    # no singularity, no null.
    v0 = patterns.vortex_phase(SHAPE, l=0)
    intensity_v0, _ = simulate.simulate_far_field(v0, WAVELENGTH_M, PIXEL_PITCH_M)
    check("vortex l=0 has no on-axis null (degenerates to flat phase)",
          simulate.on_axis_intensity(intensity_v0) > 0.9)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {failures}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
