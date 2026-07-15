from tqdm import tqdm
import time
import numpy as np
import matplotlib.pyplot as plt


def measure_polarized_spectra(
    polarizer, qwp, spec,
    pol_start=0, pol_step_num=25,
    qwp_start=0, qwp_stop=180, qwp_step=9,
    flip_mount=None,
    save_txt=False,
    plot=False,
    unit="cm-1",
):
    """
    Measure polarized Raman spectra over:
        - Polarizer angles
        - QWP angles
    """

    # ---------- Define angle steps (raw angles, not modded) ----------
    pol_angles = np.linspace(pol_start, pol_start + 360, pol_step_num)
    qwp_angles = np.arange(qwp_start, qwp_stop + 1, qwp_step)

    # ---------- Get x-axis once ----------
    x_nm, x_eV, x_cm, test_spec = spec.acquire_spectrum(plot_unit=None)
    n_points = len(test_spec)

    if unit == "nm":
        x_axis = x_nm
        xlabel = "Wavelength (nm)"
    elif unit == "eV":
        x_axis = x_eV
        xlabel = "Energy (eV)"
    elif unit == "cm-1":
        x_axis = x_cm
        xlabel = "Raman Shift (cm⁻¹)"
    else:
        raise ValueError("unit must be: 'nm', 'eV', or 'cm-1'")

    spectra = np.zeros((len(qwp_angles), len(pol_angles), n_points))

    print("\n===== Polarized Raman Scan Started =====")

    # ---------- flip mount ----------
    if flip_mount is not None:
        print("[Flip mount] Moving out the optic...")
        flip_mount.move_to_state(1)
        time.sleep(0.3)

    # ---------- spectrometer checks ----------
    spec.print_spectrometer_parameters()
    spec.check_ccd_temperature()

    
    # ---------- Progress bar ----------
    total_steps = len(qwp_angles) * len(pol_angles)
    pbar = tqdm(total=total_steps, ncols=80, desc="Scanning")


    
    # ---------- MAIN LOOP ----------
    for i_qwp, qwp_angle in enumerate(qwp_angles):
        print(f"\nSetting QWP → {qwp_angle:.1f}°")
        qwp.move_to(qwp_angle, blocking=True)

        for i_pol, pol_angle in enumerate(pol_angles):
            polarizer.move_to(pol_angle, blocking=True)
            _, _, _, spectrum = spec.acquire_spectrum(plot_unit=unit)
            spectra[i_qwp, i_pol] = spectrum

            pbar.set_postfix(qwp=f"{qwp_angle:.1f}°", pol=f"{pol_angle:.1f}°")
            pbar.update(1)

        print(f"--- Finished QWP = {qwp_angle}° ---")

    print("\n===== Polarized Raman Scan Completed Successfully =====")

    return {
        "pol_angles": pol_angles,
        "qwp_angles": qwp_angles,
        "x_axis": x_axis,
        "spectra": spectra,
        "xlabel": xlabel,
    }


def preview_spectra(result, qwp_idx=0):
    x = result["x_axis"]
    spectra = result["spectra"]
    plt.figure()
    for i_pol in range(spectra.shape[1]):
        plt.plot(x, spectra[qwp_idx, i_pol], alpha=0.6)
    plt.title(f"Preview: All analyzer angles @ QWP index {qwp_idx}")
    plt.xlabel(result["xlabel"])
    plt.ylabel("Intensity (a.u.)")
    plt.show()


def save_all_spectra_raw(result, prefix="PolarizedScan"):
    np.savez(
        f"{prefix}.npz",
        pol_angles=result["pol_angles"],
        qwp_angles=result["qwp_angles"],
        x_axis=result["x_axis"],
        spectra=result["spectra"],
    )
    print(f"[Saved] {prefix}.npz")
