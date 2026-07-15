"""Combine phase overlays. Additive superposition, matching vendor SLM software
(e.g. HOLOEYE's "Beam Manipulation" overlay sums steering + focusing terms)
rather than interleaving/multiplexing pixels."""

import numpy as np


def sum_phases(*phases):
    """Elementwise sum of any number of same-shape phase arrays (radians)."""
    total = np.zeros_like(phases[0], dtype=np.float64)
    for phase in phases:
        total = total + phase
    return total


def wrap_phase(phase):
    """Wrap phase (radians) into [0, 2*pi) for grayscale encoding."""
    return np.mod(phase, 2 * np.pi)
