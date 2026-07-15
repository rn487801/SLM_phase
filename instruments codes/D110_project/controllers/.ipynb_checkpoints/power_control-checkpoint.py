import time

# EXPECTED: user will pass fm, pm1, pm2, nd explicitly
# Avoid using undefined globals as function defaults


def set_power(setpoint, tolerance, pm, motor, delay=None, max_steps=2000, unit=None, tolerance_in_percent=False):
    """
    Adjust ND filter motor until the measured power matches the setpoint.

    pm     : PowerMeter object with get_power()
    motor  : NDFilterMotor object with step_motor(steps, direction), enable(), disable()
    """
    if tolerance_in_percent == True:
        tolerance = setpoint*tolerance/100
    if unit is not None
        if unit == "uW" or unit =="uw":
            setpoint = setpoint*1e-6
            if not tolerance_in_percent:
                tolerance = tolerance*1e-6
        elif unit == "mW" or unit == "mw":
            setpoint = setpoint*1e-3
            if not tolerance_in_percent:
                tolerance = tolerance*1e-3

    motor.enable()

    for _ in range(max_steps):
        power = pm.get_power()
        error = setpoint - power

        if abs(error) <= tolerance:
            motor.disable()
            break

        # If measured power is too low → rotate BACK
        if error > 0:
            motor.step_motor(1, True, delay=delay)
        else:
            motor.step_motor(1, False, delay=delay)

    motor.disable()
    time.sleep(1)

    return power, error



def set_source_power(setpoint, tolerance, flip_mount, pm, motor, delay=None, unit=None, tolerance_in_percent=False):
    """
    Adjusts *source* power by blocking the beam and reading pm.
    """
    flip_mount.move_to_state(0)  # Block the beam
    time.sleep(1)

    power, error = set_power(setpoint, tolerance, pm, motor, delay=delay, unit=unit, tolerance_in_percent=tolerance_in_percent)

    flip_mount.move_to_state(1)  # Unblock
    time.sleep(0.5)

    print(f"[Source] Target reached: {power:.6f} W (error {error:.3e})")
    return power, error



def set_sample_power(setpoint, tolerance, flip_mount, pm_source, pm_sample, motor, delay=None, unit=None, tolerance_in_percent=False):
    """
    Adjust power until *sample-side* meter reads the setpoint.

    Also reports the corresponding *source* power.
    """
    flip_mount.move_to_state(1)  # Unblock
    time.sleep(1)

    sample_power, error = set_power(setpoint, tolerance, pm_sample, motor, delay=delay, unit=unit, tolerance_in_percent=tolerance_in_percent)

    flip_mount.move_to_state(0)  # Block
    time.sleep(1)

    source_power = pm_source.get_power()

    return sample_power, error, source_power



def power_conversion(power_set, tolerance, flip_mount, pm_source, pm_sample, motor, delay=None, unit=None, tolerance_in_percent=False):
    """
    Convert a list of desired sample powers to:
        - actual sample power
        - corresponding source power

    Returns two lists: (sample_power_list, source_power_list)
    """
    sample_power_list = []
    source_power_list = []

    for target in power_set:
        sp, _, src = set_sample_power(
            target, tolerance, flip_mount, pm_source, pm_sample, motor, delay=delay, unit=unit, tolerance_in_percent=tolerance_in_percent
        )
        sample_power_list.append(sp)
        source_power_list.append(src)

    return sample_power_list, source_power_list



def fix_power_conversion(func, parameters, setpoint, tolerance,
                         flip_mount, pm_source, pm_sample, motor, delay=None, unit=None, tolerance_in_percent=False):
    """
    For each parameter, run an operation and then enforce a fixed sample power.

    Example:
        func = rotate_waveplate
        parameters = [0, 10, 20, ...]
        after rotating → re-adjust the sample power to fixed setpoint.

    Returns: (sample_power_list, source_power_list)
    """
    sample_power_list = []
    source_power_list = []

    for p in parameters:
        func(p)  # perform operation (e.g., rotation)

        sp, _, src = set_sample_power(
            setpoint, tolerance, flip_mount, pm_source, pm_sample, motor, delay=delay, unit=unit, tolerance_in_percent=tolerance_in_percent
        )

        sample_power_list.append(sp)
        source_power_list.append(src)

    return sample_power_list, source_power_list
