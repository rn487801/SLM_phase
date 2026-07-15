# analysis/peak_fitting.py
import warnings
import numpy as np
from scipy.optimize import curve_fit, OptimizeWarning
from tqdm import tqdm

# -----------------------------
# Models
# -----------------------------
def gaussian(x, amp, cen, wid):
    """Gaussian: amp * exp(-(x-cen)^2/(2*wid^2)). wid = sigma."""
    x = np.asarray(x)
    return amp * np.exp(-(x - cen)**2 / (2.0 * wid**2))

def lorentzian(x, amp, cen, wid):
    """amp * (wid^2) / ((x-cen)^2 + wid^2)"""
    x = np.asarray(x)
    return amp * (wid**2) / ((x - cen)**2 + wid**2)

def polynomial(x, *coeffs):
    """Polynomial background: c0 + c1*x + c2*x^2 + ..."""
    x = np.asarray(x)
    total = np.zeros_like(x, dtype=float)
    for i, c in enumerate(coeffs):
        total += c * x**i
    return total


def n_peak_model(x, *params, model="gaussian"):
    """
    Generic model: polynomial background + N Gaussians.

    params layout:
      [poly0, poly1, ..., amp1, cen1, wid1, amp2, cen2, wid2, ...]
    n_peak_model.n_poly and n_peak_model.n_peaks MUST be set before calling.
    """
    n_poly = getattr(n_peak_model, "n_poly", None)
    n_peaks = getattr(n_peak_model, "n_peaks", None)
    if n_poly is None or n_peaks is None:
        raise RuntimeError("n_peak_model.n_poly and .n_peaks must be set")

    expected = n_poly + 3 * n_peaks
    if len(params) != expected:
        raise ValueError(f"Expected {expected} params, got {len(params)}")

    # Background
    poly_params = params[:n_poly]
    total = polynomial(x, *poly_params)

    # Peaks
    p_start = n_poly
    for k in range(n_peaks):
        pk = params[p_start + 3*k : p_start + 3*(k+1)]
        amp, cen, wid = pk

        if model == "gaussian":
            total += gaussian(x, amp, cen, wid)
        elif model == "lorentzian":
            total += lorentzian(x, amp, cen, wid)
        else:
            raise ValueError(f"Unknown model '{model}'")

    return total


# -----------------------------
# Tools
# -----------------------------
def clean_data(x, y):
    """Remove NaNs/infs in y and ensure x,y aligned."""
    x = np.asarray(x)
    y = np.asarray(y)

    if x.shape != y.shape:
        raise ValueError("x and y must have the same shape")

    mask = np.isfinite(y)
    return x[mask], y[mask]


def crop_range(x, y, xmin, xmax):
    """Return x,y cropped to [xmin, xmax]. Works if x is monotonic."""
    x = np.asarray(x)
    y = np.asarray(y)
    mask = (x >= xmin) & (x <= xmax)
    return x[mask], y[mask]


# -----------------------------
# Master fitting function
# -----------------------------
def fit_n_peaks(
    x, y,
    fit_range,
    init_peaks,              # list of [amp, cen, wid] for each peak
    init_poly=None,          # polynomial background coeffs; e.g. [c0] or [c0,c1]
    bounds=None,
    model="gaussian", 
    maxfev=20000
):
    """
    Fit polynomial background + N Gaussian peaks.

    Returns (popt, pcov) or (None, None) if fitting fails.
    """
    # defensive defaults
    if init_poly is None:
        init_poly = [0.0, 0.0]  # default to linear background (change if you want)

    x, y = clean_data(x, y)
    x, y = crop_range(x, y, fit_range[0], fit_range[1])

    n_peaks = len(init_peaks)
    n_poly = len(init_poly)

    # set attributes for the model
    n_peak_model.n_peaks = n_peaks
    n_peak_model.n_poly = n_poly

    # Build initial parameter vector p0
    p0 = list(init_poly)
    for peak in init_peaks:
        p0.extend(list(peak))

    # Default bounds
    if bounds is None:
        lower = [-np.inf] * len(p0)
        upper = [np.inf] * len(p0)
        bounds = (lower, upper)

    try:
        # treat OptimizeWarning as an error so we go to except
        with warnings.catch_warnings():
            warnings.simplefilter("error", OptimizeWarning)
        
            popt, pcov = curve_fit(
                lambda xx, *pp: n_peak_model(xx, *pp, model=model),
                x, y,
                p0=p0, bounds=bounds, maxfev=maxfev
            )

    except (RuntimeError, OptimizeWarning, ValueError) as e:
        # Could log e for debugging
        # print(f"[fit_n_peaks] Fit failed: {e}")
        return None, None

    return popt, pcov


def fit_all_spectra(
    result,
    fit_range,
    init_peaks,
    init_poly=None,
    bounds=None,
    return_area=False,
    model="gaussian",
    maxfev=20000
):
    """
    Fit every spectrum inside result['spectra'].

    Parameters
    ----------
    result : dict from measure_polarized_spectra()
    fit_range : [low, high] in same unit as x_axis
    init_peaks : list of initial peak guesses [[amp, center, width], ...]
    init_poly : initial background params [c0, c1], default linear
    bounds : scipy curve_fit bounds
    return_area : if True return peak areas, else peak amplitudes
    model : "gaussian" or "lorentzian"
    """

    if init_poly is None:
        init_poly = [0.0, 0.0]

    x = result["x_axis"]
    spectra = result["spectra"]
    n_qwp, n_pol, n_points = spectra.shape
    n_peaks = len(init_peaks)

    # Output
    peak_matrix = np.full((n_qwp, n_pol, n_peaks), np.nan)
    center_matrix = np.full((n_qwp, n_pol, n_peaks), np.nan)
    width_matrix  = np.full((n_qwp, n_pol, n_peaks), np.nan)

    popt_matrix = np.empty((n_qwp, n_pol), dtype=object)

    # Create mask for fit range
    lo, hi = fit_range
    mask = (x >= lo) & (x <= hi)
    if not np.any(mask):
        raise ValueError("fit_range does not overlap with x_axis")

    x_fit = x[mask]

    total = n_qwp * n_pol
    pbar = tqdm(total=total, ncols=80, desc="Fitting spectra")

    prev_popt = None   # for smart warm-starting

    for i_qwp in range(n_qwp):
        for i_pol in range(n_pol):

            y = spectra[i_qwp, i_pol, :][mask]

            # Smart initial guess
            if prev_popt is None:
                init = init_peaks
            else:
                # use previous center/width as guess, keep amp from init_peaks
                init = []
                for k in range(n_peaks):
                    _, c0, w0 = init_peaks[k]
                    amp_prev, center_prev, width_prev = prev_popt[k]
                    init.append([amp_prev, center_prev, width_prev])

            popt, pcov = fit_n_peaks(
                x_fit, y, fit_range=fit_range,
                init_peaks=init,
                init_poly=init_poly,
                bounds=bounds,
                model=model,
                maxfev=maxfev
            )

            popt_matrix[i_qwp, i_pol] = popt

            if popt is not None:
                params = np.array(popt[len(init_poly):]).reshape(n_peaks, 3)

                amps   = params[:, 0]
                centers = params[:, 1]
                widths  = params[:, 2]

                if return_area:
                    areas = amps * widths * np.sqrt(2*np.pi)
                    peak_matrix[i_qwp, i_pol] = areas
                else:
                    peak_matrix[i_qwp, i_pol] = amps

                center_matrix[i_qwp, i_pol] = centers
                width_matrix[i_qwp, i_pol] = widths

                prev_popt = params   # update warm start

            pbar.update(1)

    pbar.close()

    return {
        "peak_matrix": peak_matrix,
        "center_matrix": center_matrix,
        "width_matrix": width_matrix,
        "popt_matrix": popt_matrix,
        "fit_range": fit_range
    }
