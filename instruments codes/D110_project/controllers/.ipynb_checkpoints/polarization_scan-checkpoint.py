import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time

def polarization_scan(pm, polarizer, qwp, flip_mount, laser_wavelength=532, save=True,
                      pol_start=0, qwp_start=0, pol_step_num=25, qwp_stop=180, qwp_step=9):
    """
    Perform polarization scan using QWP (stage2) and polarizer (stage1).
    """
    # --- Step settings ---
    pol_steps = np.linspace(pol_start, pol_start + 360, pol_step_num)
    qwp_steps = np.arange(qwp_start, qwp_stop + 1, qwp_step)

    pol_steps = np.mod(pol_steps, 360)
    qwp_steps = np.mod(qwp_steps, 360)

    print(f"Polarizer steps: {pol_steps}")
    print(f"QWP steps: {qwp_steps}")

    # --- Setup instruments ---
    pm.set_wavelength(laser_wavelength * 1e-9)
    flip_mount.move_to_state(1)  # Beam ON

    power_matrix = np.zeros((len(pol_steps), len(qwp_steps)))

    plt.ion()
    for j, qwp_angle in enumerate(qwp_steps):
        print(f"\nSetting QWP to {qwp_angle:.1f}°")
        qwp.move_to(qwp_angle, blocking=True)
        time.sleep(0.2)

        for i, pol_angle in enumerate(pol_steps):
            polarizer.move_to(pol_angle, blocking=True)
            time.sleep(0.2)
            power = pm.get_power()
            power_matrix[i, j] = power
            print(f"  Polarizer {pol_angle:.1f}°, QWP {qwp_angle:.1f}° → {power:.4e} W")

        # --- Polar plot for this QWP ---
        fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
        ax.set_title(f"QWP = {qwp_angle:.1f}°")
        ax.set_theta_direction(-1)
        ax.set_theta_zero_location("N")

        theta = np.deg2rad(pol_steps)
        r = power_matrix[:, j]
        theta = np.append(theta, theta[0])
        r = np.append(r, r[0])
        ax.plot(theta, r, 'o-', label=f"QWP {qwp_angle:.1f}°")
        ax.legend(loc='upper right')
        plt.show(block=False)
        plt.pause(0.5)

    plt.ioff()

    df = pd.DataFrame(power_matrix,
                      index=[f"{a1:.1f}" for a1 in pol_steps],
                      columns=[f"{a2:.1f}" for a2 in qwp_steps])

    if save:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_filename = f"power_map_{timestamp}.csv"
        fig_filename = f"polarization_map_{timestamp}.png"
        df.to_csv(csv_filename)
        plt.savefig(fig_filename, dpi=300, bbox_inches="tight")
        print(f"Data saved to '{csv_filename}' and '{fig_filename}'")

    # --- Combined plot ---
    fig2, ax2 = plt.subplots(subplot_kw={'projection': 'polar'})
    ax2.set_title("All QWP Angles - Polar Plot")
    ax2.set_theta_direction(-1)
    ax2.set_theta_zero_location("N")

    for j, qwp_angle in enumerate(qwp_steps):
        theta = np.deg2rad(pol_steps)
        r = power_matrix[:, j]
        theta = np.append(theta, theta[0])
        r = np.append(r, r[0])
        ax2.plot(theta, r, label=f"{qwp_angle:.1f}°")

    ax2.legend(bbox_to_anchor=(1.2, 1.0))
    plt.show()

    return df
