"""Predict (via slm_toolbox.simulate) what several phase patterns will
actually produce optically -- no SLM required. Renders the SLM phase pattern
and its simulated far-field intensity side by side for a handful of cases:
vortex (doughnut with a hard on-axis null), axicon (ring), a plain lens
(focused spot), and vortex+lens (an off-null focused doughnut).

Run: python examples/simulate_far_field_gallery.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slm_toolbox import patterns, compose, render, simulate

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SHAPE = (256, 256)
WAVELENGTH_M = 1064e-9
PIXEL_PITCH_M = 8e-6
WAIST_M = 60e-6


def save_pair(name, phase, illumination=None):
    wrapped = compose.wrap_phase(phase)
    phase_gray = render.phase_to_gray(wrapped, bit_depth=8)
    render.save_pattern(os.path.join(OUT_DIR, f"{name}_phase.png"), phase_gray)

    intensity, angular_pixel_rad = simulate.simulate_far_field(
        phase, WAVELENGTH_M, PIXEL_PITCH_M, amplitude=illumination)
    # gamma-compress for display (diffraction patterns have huge dynamic range)
    display_img = np.clip(intensity, 0, 1) ** 0.35
    gray = render.phase_to_gray(display_img * 2 * np.pi, bit_depth=8)  # reuse phase_to_gray as a 0..1->0..255 mapper
    render.save_pattern(os.path.join(OUT_DIR, f"{name}_far_field.png"), gray)

    on_axis = simulate.on_axis_intensity(intensity)
    print(f"{name}: on-axis intensity = {on_axis:.4g}, angular px = {angular_pixel_rad * 1e6:.2f} urad")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    illum = simulate.gaussian_illumination(SHAPE, WAIST_M, PIXEL_PITCH_M)

    save_pair("vortex_l3", patterns.vortex_phase(SHAPE, l=3), illumination=illum)
    save_pair("flat", np.zeros(SHAPE), illumination=illum)
    save_pair(
        "axicon",
        patterns.axicon_phase(SHAPE, cone_angle_rad=np.deg2rad(1.5), wavelength_m=WAVELENGTH_M,
                               pixel_pitch_m=PIXEL_PITCH_M, sign=1.0),
        illumination=illum,
    )
    save_pair(
        "vortex_l3_plus_lens",
        compose.sum_phases(
            patterns.vortex_phase(SHAPE, l=3),
            patterns.fresnel_lens_phase(SHAPE, focal_length_m=2.0, wavelength_m=WAVELENGTH_M,
                                         pixel_pitch_m=PIXEL_PITCH_M, converging=True),
        ),
        illumination=illum,
    )
    print(f"wrote phase + predicted far-field pairs to {OUT_DIR}")


if __name__ == "__main__":
    main()
