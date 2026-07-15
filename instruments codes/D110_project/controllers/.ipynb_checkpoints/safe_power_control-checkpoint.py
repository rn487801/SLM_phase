def set_power(
    setpoint, 
    tolerance, 
    pm, 
    motor, 
    damage_threshold,
    delay=None,
    max_steps=3000
):
    """
    Adaptive-speed power control with safety threshold.
    """
    motor.enable()

    for step_count in range(max_steps):
        power = pm.get_power()
        error = setpoint - power

        # --- HARD SAFETY CHECK ---
        if power >= damage_threshold:
            print(f"⚠️ EMERGENCY STOP: Power hit {power:.6f} W ≥ damage limit {damage_threshold:.6f} W")
            motor.disable()
            raise RuntimeError("ND filter rotation stopped for safety.")

        # --- Check if target reached ---
        if abs(error) <= tolerance:
            motor.disable()
            return power, error

        # ===== SPEED OPTIMIZATION =====
        abs_err = abs(error)

        # Choose step size adaptively
        if abs_err > 0.5 * setpoint:
            step_size = 8
        elif abs_err > 0.2 * setpoint:
            step_size = 4
        elif abs_err > 0.05 * setpoint:
            step_size = 2
        else:
            step_size = 1  # final fine adjustments

        # Predictive soft safe-check
        predicted_power = power + (error * 0.1)
        if predicted_power > damage_threshold * 0.95:
            print("⚠️ Predictive safety stop: next corrections may exceed safe power.")
            motor.disable()
            raise RuntimeError("Approaching unsafe region, stopping ND filter.")

        # === Move motor ===
        direction = True if error > 0 else False
        motor.step_motor(step_size, direction, delay=delay)

    motor.disable()
    raise RuntimeError("Power stabilization failed: exceeded max_steps")

def set_sample_power(setpoint, tolerance, flip_mount,
                     pm_source, pm_sample, motor,
                     damage_threshold, delay=None):

    flip_mount.move_to_state(1)  # Unblock
    time.sleep(1)

    sample_power, error = set_power(
        setpoint=setpoint,
        tolerance=tolerance,
        pm=pm_sample,
        motor=motor,
        damage_threshold=damage_threshold,
        delay=delay
    )

    flip_mount.move_to_state(0)  # Block
    time.sleep(1)

    source_power = pm_source.get_power()
    return sample_power, error, source_power

def power_conversion(power_set, tolerance, flip_mount,
                     pm_source, pm_sample, motor,
                     damage_threshold, delay=None):

    sample_list = []
    source_list = []

    for target in power_set:
        sp, _, src = set_sample_power(
            target, tolerance,
            flip_mount,
            pm_source, pm_sample, motor,
            damage_threshold,
            delay=delay
        )
        sample_list.append(sp)
        source_list.append(src)

    return sample_list, source_list
