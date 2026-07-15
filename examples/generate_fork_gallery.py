"""Regenerate the forked vortex+grating holograms (vortex phase + blazed
grating, summed and wrapped) for L = -5..5, for visual parity comparison
against the existing Mathematica outputs `grating L=<n>_.jpg`.

Run: python examples/generate_fork_gallery.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slm_toolbox import patterns, compose, render

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SHAPE = (512, 512)
GRATING_PERIOD_PX = 12


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for l in range(-5, 6):
        phase = compose.sum_phases(
            patterns.vortex_phase(SHAPE, l=l),
            patterns.blazed_grating_phase(SHAPE, period_px=GRATING_PERIOD_PX, angle_deg=0.0),
        )
        gray = render.phase_to_gray(compose.wrap_phase(phase))
        out_path = os.path.join(OUT_DIR, f"fork_L={l}.png")
        render.save_pattern(out_path, gray)
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
