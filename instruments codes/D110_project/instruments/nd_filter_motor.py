import nidaqmx
import time

class NDFilterMotor:
    def __init__(self, dev="Dev3", delay=0.000):
        self.dev = dev
        self.delay = delay

        # Create NI-DAQ tasks
        self.pul_task = nidaqmx.Task()
        self.dir_task = nidaqmx.Task()
        self.ena_task = nidaqmx.Task()

        # Assign channels
        self.pul_task.do_channels.add_do_chan(f"{dev}/port2/line0")  # PUL
        self.dir_task.do_channels.add_do_chan(f"{dev}/port2/line2")  # DIR
        self.ena_task.do_channels.add_do_chan(f"{dev}/port2/line1")  # ENA

        # Optional: default disable at start
        self.disable()

    def enable(self):
        """Enable the motor driver"""
        self.ena_task.write(False)

    def disable(self):
        """Disable (brake) the motor driver"""
        self.ena_task.write(True)

    def step_motor(self, steps, direction,delay=None):
        """Move given number of steps with direction 0 or 1"""
        if delay is not None:
            self.delay = delay
        self.dir_task.write(direction)
        for _ in range(steps):
            self.pul_task.write(True)
            time.sleep(self.delay)
            self.pul_task.write(False)
            time.sleep(self.delay)

    def close(self):
        """Clean up NI tasks"""
        self.pul_task.close()
        self.dir_task.close()
        self.ena_task.close()