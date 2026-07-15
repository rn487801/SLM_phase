# andor_spectrometer.py
import numpy as np
import matplotlib.pyplot as plt
import pylablib as pll
from pylablib.devices import Andor


class AndorSpectrometer:
    def __init__(self,
                 shamrock_dll="C:/Program Files/Andor SDK/Shamrock64",
                 sdk2_dll="C:/Program Files/Andor SDK",
                 temperature=-75,
                 fan_mode="full",
                 exposure_time=0.5,
                 grating=1,
                 grating_offset=-32,
                 laser_wavelength=532):
        """
        Initialize Andor camera and spectrometer.
        """
        pll.par["devices/dlls/andor_shamrock"] = shamrock_dll
        pll.par["devices/dlls/andor_sdk2"] = sdk2_dll

        self.cam = Andor.AndorSDK2Camera(temperature=temperature, fan_mode=fan_mode)
        self.spec = Andor.ShamrockSpectrograph()
        self.laser_wavelength = laser_wavelength
        self.exposure_time = exposure_time

        # Initialize
        self.cam.set_cooler()
        self.cam.set_temperature(temperature, enable_cooler=True)
        self.cam.setup_shutter("auto")
        self.cam.set_read_mode("fvb")

        # Spectrograph setup
        self.spec.set_grating(grating)
        self.spec.set_grating_offset(grating_offset)
        self.spec.setup_pixels_from_camera(self.cam)

        print(f"[Init] Cooler: {self.cam.is_cooler_on()}, "
              f"T={self.cam.get_temperature()} °C, Status={self.cam.get_temperature_status()}")

    def center_setting(self, center_value=800, unit="nm", laser_wavelength = None):
        """Set spectrograph center wavelength."""
        if unit == "nm":
            center_wavelength = center_value
        elif unit == "eV":
            center_wavelength = 1240 / center_value
        elif unit == "cm-1":
            if laser_wavelength is not None:
                self.laser_wavelength = laser_wavelength
            center_wavelength = 1 / ((1 / self.laser_wavelength) - center_value / 1e7)
        else:
            raise ValueError("unit must be 'nm', 'eV', or 'cm-1'")
        self.spec.set_wavelength(center_wavelength * 1e-9)  # meters

    def set_exposure_time(self, exposure_time):
        """Set exposure time in seconds."""
        self.exposure_time = exposure_time
        self.cam.set_exposure(exposure_time)
        print(f"[Exposure] Exposure time set to {exposure_time} s")


    def set_grating(self, grating):
        """
        Set grating by its blaze value.
        grating = 150  -> grating #1
        grating = 1200 -> grating #2
        """
        if grating == 150:
            self.spec.set_grating(1)
            self.spec.set_grating_offset(-25)
            print("[Grating] Set to 150 g/mm")
        elif grating == 1200:
            self.spec.set_grating(2)
            self.spec.set_grating_offset(-32)
            print("[Grating] Set to 1200 g/mm")
        else:
            raise ValueError("Grating must be 150 or 1200")

    def check_ccd_temperature(self):
        temp = self.cam.get_temperature()
        status = self.cam.get_temperature_status()
        print(f"[CCD] Temperature = {temp} °C, Status = {status}")
        return temp, status
    
    def print_spectrometer_parameters(self):
        print("[Spectrometer Parameters]")
        print(" Exposure time:", self.cam.get_exposure())
        print(" Grating:",        self.spec.get_grating())
        print(" Grating offset:", self.spec.get_grating_offset())
        print(" Center:",         self.spec.get_wavelength())

    def acquire_spectrum(self, plot_unit=None, save=False):
        """Acquire a single frame and return the spectrum."""
        self.cam.set_exposure(self.exposure_time)
        frame = self.cam.snap()
        spectrum = frame.mean(axis=0) if frame.ndim > 1 else frame

        # X-axis conversions
        wavelengths = self.spec.get_calibration() * 1e9  # nm
        x_nm = wavelengths[:len(spectrum)]
        x_eV = 1240 / x_nm
        x_cm = (1e7) * (1 / self.laser_wavelength - 1 / x_nm)

        if plot_unit is not None:
            if plot_unit == "nm":
                self._plot(x_nm, spectrum, "Wavelength (nm)", "PL Spectrum (nm)")
            elif plot_unit == "eV":
                self._plot(x_eV, spectrum, "Energy (eV)", "PL Spectrum (eV)", invert=True)
            elif plot_unit == "cm-1":
                self._plot(x_cm, spectrum, "Raman Shift (cm⁻¹)", "Raman Spectrum")

        if save:
            np.savetxt(f"Spectrum_Exp{self.exposure_time}s.txt",
                       np.column_stack([x_nm, x_eV, x_cm, spectrum]),
                       header="Wavelength (nm)\tEnergy (eV)\tRaman shift(cm-1)\tIntensity (a.u.)")

        return x_nm, x_eV, x_cm, spectrum

    def _plot(self, x, y, xlabel, title, invert=False):
        plt.figure()
        plt.plot(x, y, lw=1.5)
        plt.xlabel(xlabel)
        plt.ylabel("Intensity (a.u.)")
        plt.title(title)
        if invert:
            plt.gca().invert_xaxis()
        plt.show()

    def close(self):
        """Close the device connections."""
        self.cam.close()
        self.spec.close()
        print("[AndorSpectrometer] Devices closed.")


    def live_spectrum(self, unit="nm"):
        """
        Continuously acquire and update a live spectrum plot.
        Press 'q' to stop.
        Only works on Windows (msvcrt).
        """
        import msvcrt
        plt.ion()

        # Initial acquisition
        self.cam.set_exposure(self.exposure_time)
        frame = self.cam.snap()
        spectrum = frame.mean(axis=0) if frame.ndim > 1 else frame

        # Compute x-axis choices
        wavelengths = self.spec.get_calibration() * 1e9
        x_nm = wavelengths[:len(spectrum)]
        x_eV = 1240 / x_nm
        x_cm = (1e7) * (1 / self.laser_wavelength - 1 / x_nm)

        if unit == "nm":
            x = x_nm
            xlabel = "Wavelength (nm)"
        elif unit == "eV":
            x = x_eV
            xlabel = "Energy (eV)"
        elif unit == "cm-1":
            x = x_cm
            xlabel = "Raman Shift (cm⁻¹)"
        else:
            raise ValueError("unit must be 'nm', 'eV', or 'cm-1'")

        # Setup figure
        fig, ax = plt.subplots()
        line, = ax.plot(x, spectrum, lw=1.5)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Intensity (a.u.)")
        if unit == "eV":
            ax.invert_xaxis()
        fig.canvas.draw()
        fig.canvas.flush_events()

        print("Live spectrum started. Press 'q' to stop.\n")

        # Main loop
        while True:
            # Acquire frame
            frame = self.cam.snap()
            spectrum = frame.mean(axis=0) if frame.ndim > 1 else frame

            # Update line
            line.set_ydata(spectrum)

            # Refresh plot
            fig.canvas.draw()
            fig.canvas.flush_events()

            # Quit on 'q'
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'q':
                    print("Live mode stopped.")
                    break


if __name__ == "__main__":
    # Example usage (only runs if you execute this file directly)
    spec = AndorSpectrometer()
    spec.center_setting(1370, "cm-1")
    spec.acquire_spectrum(plot_unit="cm-1", save=True)
    spec.close()
