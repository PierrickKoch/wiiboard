#! /usr/bin/env python
""" Wii Fit Balance Board (WBB) in python

usage: wiiboard.py [-d] [address] 2> wiiboard.log > wiiboard.txt
tip: use `hcitool scan` to get a list of devices addresses

You only need to install `python-bluez` or `python-bluetooth` package.

LICENSE LGPL <http://www.gnu.org/licenses/lgpl.html>
        (c) Nedim Jackman 2008 (c) Pierrick Koch 2016
"""
import time
import logging
import collections
import bluetooth

# Wiiboard Parameters
CONTINUOUS_REPORTING    = b'\x04'
COMMAND_LIGHT           = b'\x11'
COMMAND_REPORTING       = b'\x12'
COMMAND_REQUEST_STATUS  = b'\x15'
COMMAND_REGISTER        = b'\x16'
COMMAND_READ_REGISTER   = b'\x17'
INPUT_STATUS            = b'\x20'
INPUT_READ_DATA         = b'\x21'
EXTENSION_8BYTES        = b'\x32'
BUTTON_DOWN_MASK        = 0x08
LED1_MASK               = 0x10
BATTERY_MAX             = 200.0
TOP_RIGHT               = 0
BOTTOM_RIGHT            = 1
TOP_LEFT                = 2
BOTTOM_LEFT             = 3
BLUETOOTH_NAME          = "Nintendo RVL-WBC-01"
# WiiboardSampling Parameters
N_SAMPLES               = 200
N_LOOP                  = 10
T_SLEEP                 = 2

# initialize the logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler() # or RotatingFileHandler
handler.setFormatter(logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s] %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO) # or DEBUG

b2i = lambda b: int(b.encode("hex"), 16)

def discover(duration=6, prefix=BLUETOOTH_NAME):
    logger.info("Scan Bluetooth devices for %i seconds...", duration)
    devices = bluetooth.discover_devices(duration=duration, lookup_names=True)
    logger.debug("Found devices: %s", str(devices))
    return [address for address, name in devices if name.startswith(prefix)]

class Wiiboard:
    def __init__(self, address=None):
        self.controlsocket = bluetooth.BluetoothSocket(bluetooth.L2CAP)
        self.receivesocket = bluetooth.BluetoothSocket(bluetooth.L2CAP)
        self.calibration = [[1e4]*4]*3
        self.calibration_requested = False
        self.light_state = False
        self.button_down = False
        self.battery = 0.0
        self.running = True
        if address is not None:
            self.connect(address)
    def connect(self, address):
        logger.info("Connecting to %s", address)
        self.controlsocket.connect((address, 0x11))
        self.receivesocket.connect((address, 0x13))
        logger.debug("Sending mass calibration request")
        self.send(COMMAND_READ_REGISTER, b"\x04\xA4\x00\x24\x00\x18")
        self.calibration_requested = True
        logger.info("Wait for calibration")
        logger.debug("Connect to the balance extension, to read mass data")
        self.send(COMMAND_REGISTER, b"\x04\xA4\x00\x40\x00")
        logger.debug("Request status")
        self.status()
        self.light(0)
    def send(self, *data):
        self.controlsocket.send(b'\x52'+b''.join(data))
    def reporting(self, mode=CONTINUOUS_REPORTING, extension=EXTENSION_8BYTES):
        self.send(COMMAND_REPORTING, mode, extension)
    def light(self, on_off=True):
        self.send(COMMAND_LIGHT, b'\x10' if on_off else b'\x00')
    def status(self):
        self.send(COMMAND_REQUEST_STATUS, b'\x00')
    def calc_mass(self, raw, pos):
        # Calculates the Kilogram weight reading from raw data at position pos
        # calibration[0] is calibration values for 0kg
        # calibration[1] is calibration values for 17kg
        # calibration[2] is calibration values for 34kg
        if raw < self.calibration[0][pos]:
            return 0.0
        elif raw < self.calibration[1][pos]:
            return 17 * ((raw - self.calibration[0][pos]) /
                         float((self.calibration[1][pos] -
                                self.calibration[0][pos])))
        else: # if raw >= self.calibration[1][pos]:
            return 17 + 17 * ((raw - self.calibration[1][pos]) /
                              float((self.calibration[2][pos] -
                                     self.calibration[1][pos])))
    def check_button(self, state):
        if state == BUTTON_DOWN_MASK:
            if not self.button_down:
                self.button_down = True
                self.on_pressed()
        elif self.button_down:
            self.button_down = False
            self.on_released()
    def get_mass(self, data):
        return {
            'top_right':    self.calc_mass(b2i(data[0:2]), TOP_RIGHT),
            'bottom_right': self.calc_mass(b2i(data[2:4]), BOTTOM_RIGHT),
            'top_left':     self.calc_mass(b2i(data[4:6]), TOP_LEFT),
            'bottom_left':  self.calc_mass(b2i(data[6:8]), BOTTOM_LEFT),
        }
    def loop(self):
        logger.debug("Starting the receive loop")
        while self.running and self.receivesocket:
            data = self.receivesocket.recv(25)
            logger.debug("socket.recv(25): %r", data)
            if len(data) < 2:
                continue
            input_type = data[1]
            if input_type == INPUT_STATUS:
                self.battery = b2i(data[7:9]) / BATTERY_MAX
                # 0x12: on, 0x02: off/blink
                self.light_state = b2i(data[4]) & LED1_MASK == LED1_MASK
                self.on_status()
            elif input_type == INPUT_READ_DATA:
                logger.debug("Got calibration data")
                if self.calibration_requested:
                    length = b2i(data[4]) / 16 + 1
                    data = data[7:7 + length]
                    cal = lambda d: [b2i(d[j:j+2]) for j in [0, 2, 4, 6]]
                    if length == 16: # First packet of calibration data
                        self.calibration = [cal(data[0:8]), cal(data[8:16]), [1e4]*4]
                    elif length < 16: # Second packet of calibration data
                        self.calibration[2] = cal(data[0:8])
                        self.calibration_requested = False
                        self.on_calibrated()
            elif input_type == EXTENSION_8BYTES:
                self.check_button(b2i(data[2:4]))
                self.on_mass(self.get_mass(data[4:12]))
    def on_status(self):
        self.reporting() # Must set the reporting type after every status report
        logger.info("Status: battery: %.2f%% light: %s", self.battery*100.0,
                    'on' if self.light_state else 'off')
        self.light(1)
    def on_calibrated(self):
        logger.info("Board calibrated: %s", str(self.calibration))
        self.light(1)
    def on_mass(self, mass):
        logger.debug("New mass data: %s", str(mass))
    def on_pressed(self):
        logger.info("Button pressed")
    def on_released(self):
        logger.info("Button released")
    def close(self):
        self.running = False
        if self.receivesocket: self.receivesocket.close()
        if self.controlsocket: self.controlsocket.close()
    def __del__(self):
        self.close()
    #### with statement ####
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return not exc_type # re-raise exception if any

class WiiboardSampling(Wiiboard):
    def __init__(self, address=None, nsamples=N_SAMPLES):
        Wiiboard.__init__(self, address)
        self.samples = collections.deque([], nsamples)
    def on_mass(self, mass):
        self.samples.append(mass)
        self.on_sample()
    def on_sample(self):
        time.sleep(0.01)

# client class where we can re-define callbacks
class WiiboardPrint(WiiboardSampling):
    def __init__(self, address=None, nsamples=N_SAMPLES):
        WiiboardSampling.__init__(self, address, nsamples)
        self.nloop = 0
    def on_sample(self):
        if len(self.samples) == N_SAMPLES:
            samples = [sum(sample.values()) for sample in self.samples]
            print("%.3f %.3f"%(time.time(), sum(samples) / len(samples)))
            self.samples.clear()
            self.status() # Stop the board from publishing mass data
            self.nloop += 1
            if self.nloop > N_LOOP:
                return self.close()
            self.light(0)
            time.sleep(T_SLEEP)

if __name__ == '__main__':
    import sys
    if '-d' in sys.argv:
        logger.setLevel(logging.DEBUG)
        sys.argv.remove('-d')
    if len(sys.argv) > 1:
        address = sys.argv[1]
    else:
        wiiboards = discover()
        logger.info("Found wiiboards: %s", str(wiiboards))
        if not wiiboards:
            raise Exception("Press the red sync button on the board")
        address = wiiboards[0]
    with WiiboardPrint(address) as wiiprint:
        wiiprint.loop()
