# analysis/polarization_fitting.py
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from pathlib import Path
import matplotlib.pyplot as plt

# -----------------------------
# Incident and analyzer vectors
# -----------------------------
def incident_vec_dia(p_rad):
    """
    Return Jones vector of incident light.
    Inputs in radians.
    """
    return np.array([np.cos(np.pi/4), np.sin(np.pi/4) * np.exp(1j * p_rad)], dtype=complex)

# -----------------------------
# Waveplates (Jones)
# -----------------------------
def rotation_matrix(theta):
    """Rotation matrix R(theta). Note: R(-theta) = R(theta).T for real rotation."""
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=complex)

def incident_vec(xi_rad, p_rad):
    rot = rotation_matrix(xi_rad-np.pi/4)
    return rot @ incident_vec_dia(p_rad)


def analyzer_vec(xp_rad):
    """Linear analyzer Jones vector (unit, real). Input in radians."""
    return np.array([np.cos(xp_rad), np.sin(xp_rad)], dtype=complex)


# -----------------------------
# Raman tensors
# -----------------------------
def raman_tensor(func):
    if func == "x2-y2":
        return np.array([[1.0, 0.0], [0.0, -1.0]], dtype=complex)
    elif func == "xy":
        return np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex)
    else:
        raise ValueError("Unknown Raman mode: " + str(func))



def jones_wp(theta, delta):
    """
    Jones matrix for a waveplate with retardance delta and fast axis at angle theta.
    J = R(-theta) * diag(1, exp(i delta)) * R(theta)
    where R(theta) is rotation matrix.
    """
    R = rotation_matrix(theta)
    D = np.diag([1.0, np.exp(1j * delta)])
    # Use R.T as R(-theta) because R is real orthogonal
    return R.T @ D @ R


def jones_qwp(theta):
    """Quarter-wave plate (delta = pi/2)"""
    return jones_wp(theta, delta=np.pi / 2.0)


# -----------------------------
# Core intensity calculation
# -----------------------------
"""
def intensity_with_optics(xp_rad, xi_rad, p_rad, func,
                          A_scalar=1.0, qwp_angle_rad=None):
    
    #xp_rad, xi_rad, p_rad: angles in radians.
    #func: raman mode string e.g. "xy" or "x2-y2".
    #qwp_angle_rad: If provided, applies QWP after Raman scattering.
    #Returns a real scalar intensity.
    
    Ei = incident_vec(xi_rad, p_rad)          # 2-vector complex
    R = raman_tensor(func)                    # 2x2 complex
    Es = R @ Ei                               # scattered field before optics

    if qwp_angle_rad is not None:
        Q = jones_qwp(qwp_angle_rad)
        Es = Q @ Es

    A = analyzer_vec(xp_rad)
    amp = np.vdot(A, Es)   # A.conj().T @ Es
    return float(A_scalar * np.abs(amp)**2)
"""


def degenerate_raman_intensity(xp_rad, xi_rad, p_rad, funcs, coeffs, qwp_angle_rad=None):
    """
    Sum fields from multiple Raman tensors (degenerate channels), then apply QWP and analyzer.
    funcs : list of mode strings
    coeffs: list of real or complex coefficients (same order)
    Returns real intensity.
    """
    Ei = incident_vec(xi_rad, p_rad)
    #total_field = np.zeros(2, dtype=complex)
    total_intensity = 0
    for f, c in zip(funcs, coeffs):
        R = raman_tensor(f)
        total_field = (R @ Ei)
        
        if qwp_angle_rad is not None:
            Q = jones_qwp(qwp_angle_rad)
            total_field = Q @ total_field

        amp = np.vdot(analyzer_vec(xp_rad),total_field)
        total_intensity += c*(np.abs(amp)**2)
    """
    if qwp_angle_rad is not None:
        Q = jones_qwp(qwp_angle_rad)
        total_field = Q @ total_field
    """
    #A = analyzer_vec(xp_rad)
    #amp = np.vdot(A, total_field)
    return total_intensity


# -----------------------------
# Fit-model functions (for curve_fit)
# -----------------------------
def incident_model_deg(xp_deg, xi_deg, p, A=1.0):
    """
    Model for curve_fit where xp given in degrees.
    Converts to radians internally.
    Params to fit: xi_deg, p_deg, A if desired.
    Note: curve_fit will pass xp (array) as first param; the rest are fitted params.
    """
    xp = np.deg2rad(xp_deg)
    xi = np.deg2rad(xi_deg)

    vec = np.array([np.abs(np.vdot(analyzer_vec(x), incident_vec(xi, p)))**2 for x in xp])
    return A * vec


def degenerate_model_deg(xp_deg, xi_deg, p, c1, c2, qwp_angle_deg=None):
    """
    Example degenerate model wrapper for two coefficients c1,c2 and a fixed qwp angle (in deg).
    curve_fit expects signature f(x, param1, param2, ...). If you want qwp_angle fixed,
    use lambda xp, xi, p, c1, c2: degenerate_model_deg(xp, xi, p, c1, c2, qwp_angle_deg)
    when calling curve_fit.
    """
    xp = np.deg2rad(xp_deg)
    xi = np.deg2rad(xi_deg)
    #p = np.deg2rad(p_deg)
    qwp = qwp_angle_deg
    if qwp_angle_deg is not None:
        qwp = np.deg2rad(qwp_angle_deg)
    coeffs = [c1, c2]
    funcs = ["xy", "x2-y2"]
    out = np.array([degenerate_raman_intensity(x, xi, p, funcs, coeffs, qwp) for x in xp])
    return out

def load_polar_data(
    filepath,
    sheet_name=0,
    header=None,

    # indices
    qwp_row=0,
    qwp_start_col=1,
    pol_col=0,
    pol_start_row=1,
    data_start_row=1,
    data_start_col=1,

    # options
    qwp_reverse=False,
    qwp_offset=None,
    pol_reverse=False,
    pol_offset=None,
):
    path = Path(filepath)
    ext = path.suffix.lower()

    # Load data
    if ext == ".csv":
        df = pd.read_csv(filepath, header=header)
    elif ext == ".xlsx":
        df = pd.read_excel(filepath, sheet_name=sheet_name, header=header)
    else:
        raise ValueError("Unsupported file type: " + ext)

    # --- Extract QWP angles ---
    qwp_angle = df.iloc[qwp_row, qwp_start_col:].astype(float).values
    if qwp_reverse:
        qwp_angle = qwp_angle[::-1]
    if qwp_offset is not None:
        qwp_angle = qwp_angle - qwp_offset

    # --- Extract POL angles ---
    pol_angle = df.iloc[pol_start_row:, pol_col].astype(float).values
    if pol_reverse:
        pol_angle = pol_angle[::-1]
    if pol_offset is not None:
        pol_angle = pol_angle - pol_offset

    # --- Extract intensity matrix ---
    intensity = df.iloc[data_start_row:, data_start_col:].astype(float).values

    print("QWP angles:", qwp_angle)
    print("POL angles:", pol_angle)
    print("Intensity shape:", intensity.shape)

    return qwp_angle, pol_angle, intensity

def remove_spikes_with_180(intensity, threshold=10.0):
    """
    Detects spikes and replaces spike values with the 180° counterpart.
    Prints a message whenever a spike is replaced.
    intensity: 1D array (length N) for a single QWP scan.
    Returns cleaned intensity.
    """

    I = intensity.copy()
    N = len(I)
    half = N // 2

    # Compute median of neighbors
    I_med = np.zeros_like(I)
    for i in range(N):
        neighbors = [I[(i-1) % N], I[(i+1) % N]]
        I_med[i] = np.median(neighbors)

    # deviation
    diff = np.abs(I - I_med)

    # robust noise scale (MAD)
    noise_level = np.median(np.abs(diff - np.median(diff))) + 1e-12

    # spike = outlier
    spike_indices = np.where(diff > threshold * noise_level)[0]

    for idx in spike_indices:
        counterpart = (idx + half) % N
        print(f"[Spike] index {idx} → replaced with value at {counterpart}")
        I[idx] = I[counterpart]

    return I


def fit_multiple_incident(
    qwp_angle,
    pol_angle,
    intensity,
    p0=[0,0,1],
    spike_filter=True
):

    if spike_filter == True:
        print("Spike filter enabled")
    else:
        print("Spike filter disabled")
    
    results = []

    for i in range(len(qwp_angle)):

        # ------------------------------
        # Extract one QWP column
        # ------------------------------
        y_raw = intensity[:, i]

        # --- Fix spike noise ---
        if spike_filter:
            y = remove_spikes_with_180(y_raw)
        else:
            y = y_raw
        # Optional: normalize after spike removal
        # y = y / np.max(y)

        # ------------------------------
        # Bound selection (your logic)
        # ------------------------------
        if qwp_angle[i] < 0:
            qwp_angle[i] += 360

        if qwp_angle[i] % 180 > 90:
            bounds = ([-90, 0, 0], [90, np.pi/2, np.inf])
        else:
            bounds = ([-90, -np.pi/2, 0], [90, 0, np.inf])

        # ------------------------------
        # Curve fitting
        # ------------------------------
        popt, pcov = curve_fit(
            incident_model_deg,
            pol_angle,
            y,
            p0=p0,
            bounds=bounds,
            maxfev=20000
        )

        xi_fit, p_fit, A_fit = popt

        results.append([qwp_angle[i], xi_fit, p_fit, A_fit])

    df_results = pd.DataFrame(results, columns=["QWP_angle", "xi_deg", "p", "A"])
    return df_results


def wrap_to_pm90(angle_deg):
    # Wrap to (-180, 180]
    a = (angle_deg + 180) % 360 - 180
    
    # Now wrap to (-90, 90]
    if a > 90:
        a -= 180
    elif a < -90:
        a += 180
    return a

def incident_polarization_processing(filepath, sheet_name=0, qwp_reverse=True, pol_reverse=True, pol_offset=True ,spike_filter=True):
    #Load and arrange data
    in_qwp, in_pol, in_int = load_polar_data(filepath,sheet_name=sheet_name,qwp_reverse=qwp_reverse,pol_reverse=pol_reverse) 
    
    #Fitting
    in_fit_results = fit_multiple_incident(in_qwp,in_pol,in_int,spike_filter=spike_filter)
    print(f"Fitting results\n{in_fit_results}")

    #Polarizer calibration by QWP
    if pol_offset == True:
        in_pol_offset0 = in_fit_results.loc[in_fit_results["QWP_angle"] == 0, "xi_deg"].values[0]
        in_pol_offset180 = in_fit_results.loc[in_fit_results["QWP_angle"] == 180, "xi_deg"].values[0]
        in_pol_offset = (in_pol_offset0 + in_pol_offset180)/2
    elif type(pol_offset) == float:
        in_pol_offset = pol_offset
    else:
        in_pol_offset = 0
    
    print(f"Incident polarization offset: {in_pol_offset} deg")
    in_pol_cal = in_pol - in_pol_offset
    print(f"Calibrated Incident polarization: {in_pol_cal} deg")
    #Output calibrated fitting results
    in_fit_results["xi_deg"] = (in_fit_results["xi_deg"]- in_pol_offset).apply(wrap_to_pm90)
    print(in_fit_results)

    #Plot results
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    ax3 = ax1.twinx()
    
    ax3.spines.right.set_position(("axes", 1.2))
    
    ax1.plot(in_qwp, in_fit_results["xi_deg"], 'g-')
    ax1.set_ylim(-90,90)
    ax2.plot(in_qwp, in_fit_results["p"], 'b-')
    ax2.set_ylim(-np.pi/2,np.pi/2)
    ax3.plot(in_qwp, in_fit_results["A"], 'r-')
    
    ax1.set_xlabel("QWP angle (deg)")
    ax1.set_ylabel("xi", color='g')
    ax2.set_ylabel("p", color='b')
    ax3.set_ylabel("A", color='r')
    
    plt.show()

    return in_fit_results, in_pol_cal, in_pol_offset, in_qwp


    


