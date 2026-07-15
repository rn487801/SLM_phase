"""Generate one example of every phase-pattern type in slm_toolbox, as a
smoke test / visual reference gallery.

Run: python examples/generate_pattern_gallery.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slm_toolbox import patterns, compose, render

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SHAPE = (512, 512)

WAVELENGTH_M = 1064e-9
PIXEL_PITCH_M = 8e-6  # typical LCoS pixel pitch (e.g. Holoeye PLUTO)
WAIST_M = 40e-6


def write(name, phase):
    gray = render.phase_to_gray(compose.wrap_phase(phase))
    path = os.path.join(OUT_DIR, f"{name}.png")
    render.save_pattern(path, gray)
    print(f"wrote {path}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    write("vortex_l3", patterns.vortex_phase(SHAPE, l=3))

    write("grating_blazed", patterns.blazed_grating_phase(SHAPE, period_px=12, angle_deg=0.0))

    write(
        "lens_converging",
        patterns.fresnel_lens_phase(SHAPE, focal_length_m=0.5, wavelength_m=WAVELENGTH_M,
                                     pixel_pitch_m=PIXEL_PITCH_M, converging=True),
    )
    write(
        "lens_diverging",
        patterns.fresnel_lens_phase(SHAPE, focal_length_m=0.5, wavelength_m=WAVELENGTH_M,
                                     pixel_pitch_m=PIXEL_PITCH_M, converging=False),
    )

    write(
        "axicon_positive_bessel",
        patterns.axicon_phase(SHAPE, cone_angle_rad=np.deg2rad(0.5), wavelength_m=WAVELENGTH_M,
                               pixel_pitch_m=PIXEL_PITCH_M, sign=1.0),
    )
    write(
        "axicon_negative_ring",
        patterns.axicon_phase(SHAPE, cone_angle_rad=np.deg2rad(0.5), wavelength_m=WAVELENGTH_M,
                               pixel_pitch_m=PIXEL_PITCH_M, sign=-1.0),
    )

    lg_field = patterns.lg_mode_field(SHAPE, p=0, l=5, w0_m=WAIST_M, wavelength_m=WAVELENGTH_M,
                                       pixel_pitch_m=PIXEL_PITCH_M)
    write("lg_mode_p0_l5_phase", np.angle(lg_field))

    write(
        "hybrid_vortex_lens_grating",
        compose.sum_phases(
            patterns.vortex_phase(SHAPE, l=2),
            patterns.fresnel_lens_phase(SHAPE, focal_length_m=1.0, wavelength_m=WAVELENGTH_M,
                                         pixel_pitch_m=PIXEL_PITCH_M, converging=True),
            patterns.blazed_grating_phase(SHAPE, period_px=20, angle_deg=45.0),
        ),
    )

    write(
        "zernike_astigmatism",
        patterns.zernike_phase(SHAPE, coeffs={(2, 2): 2.0, (2, -2): 1.0}, radius_px=200),
    )

    write("checkerboard", patterns.checkerboard_phase(SHAPE, period_px=16))
    write("random_diffuser", patterns.random_phase(SHAPE, seed=0))


if __name__ == "__main__":
    main()
