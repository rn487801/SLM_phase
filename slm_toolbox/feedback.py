"""Analyze a camera frame into scalar metrics for image-feedback / closed-loop
self-calibration of the SLM.

Everything here is numpy/scipy -- OpenCV is NOT required. `cv2` is used only as
an optional accelerator for blob detection in `auto_roi` (lazily imported, with
a pure-numpy fallback), so `import slm_toolbox.feedback` works without it. Pass
`use_cv2=True` to prefer the OpenCV path when it's installed.

The two things a feedback loop needs from a frame:
  - a location/ROI of the beam or diffraction order (find_spot / auto_roi), and
  - a scalar quality metric to optimize (sharpness / peak / total), plus a
    saturation check so you never calibrate against a clipped image.
"""

import numpy as np


def saturation_fraction(frame, max_value=None):
    """Fraction of pixels at the sensor's max value -- a clipped frame gives a
    biased metric, so a feedback loop should back off exposure if this is
    nonzero. max_value defaults to the dtype max (255 for uint8)."""
    frame = np.asarray(frame)
    if max_value is None:
        max_value = np.iinfo(frame.dtype).max if np.issubdtype(frame.dtype, np.integer) else float(frame.max())
    return float(np.mean(frame >= max_value))


def _apply_roi(frame, roi):
    if roi is None:
        return frame, (0, 0)
    x0, y0, x1, y1 = roi
    return frame[y0:y1, x0:x1], (x0, y0)


def find_spot(frame, roi=None, background=None):
    """Locate and characterize the beam spot in `frame` (optionally within
    `roi`). Returns a dict:
        centroid_x, centroid_y : intensity-weighted center (full-frame px)
        peak                   : brightest pixel value
        total                  : summed intensity (background-subtracted)
        width_x, width_y       : 1/e^2-ish second-moment widths (px)
        saturated_fraction     : clipped-pixel fraction (see saturation_fraction)
    Pure numpy (image second moments) -- no fitting library needed."""
    frame = np.asarray(frame, dtype=np.float64)
    sub, (ox, oy) = _apply_roi(frame, roi)
    if background is not None:
        sub = np.clip(sub - background, 0, None)

    total = float(sub.sum())
    peak = float(sub.max()) if sub.size else 0.0
    h, w = sub.shape
    if total <= 0:
        return {"centroid_x": ox + w / 2.0, "centroid_y": oy + h / 2.0, "peak": peak,
                "total": 0.0, "width_x": 0.0, "width_y": 0.0,
                "saturated_fraction": saturation_fraction(frame)}

    ys, xs = np.indices(sub.shape)
    cx = float((xs * sub).sum() / total)
    cy = float((ys * sub).sum() / total)
    var_x = float((((xs - cx) ** 2) * sub).sum() / total)
    var_y = float((((ys - cy) ** 2) * sub).sum() / total)
    # 1/e^2 radius = 2*sigma for a Gaussian; report full 1/e^2 width = 4*sigma.
    return {
        "centroid_x": ox + cx, "centroid_y": oy + cy, "peak": peak, "total": total,
        "width_x": 4.0 * np.sqrt(var_x), "width_y": 4.0 * np.sqrt(var_y),
        "saturated_fraction": saturation_fraction(frame),
    }


def auto_roi(frame, margin=20, threshold_rel=0.5, use_cv2=False):
    """Find a bounding box around the brightest blob (e.g. the diffraction
    order to measure), so you don't have to hand-specify an ROI. Returns
    (x0, y0, x1, y1) clamped to the frame.

    Numpy path: threshold at `threshold_rel` * peak, take the bounding box of
    the above-threshold pixels, expand by `margin`. If use_cv2 and OpenCV is
    installed, uses connectedComponents to pick the largest blob (more robust
    to multiple spots); otherwise the numpy path is used."""
    frame = np.asarray(frame, dtype=np.float64)
    h, w = frame.shape
    peak = frame.max()
    if peak <= 0:
        return (0, 0, w, h)
    mask = frame >= threshold_rel * peak

    if use_cv2:
        try:
            import cv2  # optional accelerator
            n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
            if n > 1:
                largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                x, y, bw, bh = (stats[largest, cv2.CC_STAT_LEFT], stats[largest, cv2.CC_STAT_TOP],
                                stats[largest, cv2.CC_STAT_WIDTH], stats[largest, cv2.CC_STAT_HEIGHT])
                x0, y0, x1, y1 = x, y, x + bw, y + bh
                return (max(0, x0 - margin), max(0, y0 - margin),
                        min(w, x1 + margin), min(h, y1 + margin))
        except ImportError:
            pass

    ys, xs = np.where(mask)
    if xs.size == 0:
        return (0, 0, w, h)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    return (max(0, x0 - margin), max(0, y0 - margin), min(w, x1 + margin), min(h, y1 + margin))


def sharpness(frame, roi=None):
    """Image-sharpness metric to MAXIMIZE for focus/aberration correction:
    the normalized sum of squared intensity, sum(I^2)/sum(I)^2. Concentrating
    the same total light into a tighter, brighter spot increases it -- the
    standard sensorless-adaptive-optics metric. Scale-invariant to total
    brightness, so it isn't fooled by exposure/power drift."""
    frame = np.asarray(frame, dtype=np.float64)
    sub, _ = _apply_roi(frame, roi)
    total = sub.sum()
    if total <= 0:
        return 0.0
    return float((sub ** 2).sum() / (total ** 2))


def peak_intensity(frame, roi=None):
    """Simplest focus metric: the brightest pixel value. Maximize to sharpen a
    focus, but note it IS sensitive to total-power drift (unlike sharpness)."""
    sub, _ = _apply_roi(np.asarray(frame, dtype=np.float64), roi)
    return float(sub.max()) if sub.size else 0.0


def total_intensity(frame, roi=None):
    """Summed intensity in the ROI -- ~ optical power in that region. This is
    the right metric for a diffraction-efficiency (Method C) measurement:
    point the ROI at the +1 order and maximize/track this."""
    sub, _ = _apply_roi(np.asarray(frame, dtype=np.float64), roi)
    return float(sub.sum())
