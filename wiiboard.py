#! /usr/bin/env python
""" Wii Fit Balance Board (WBB) in python

usage: wiiboard.py [address] 2> wiiboard.log > wiiboard.txt
tip: use `hcitool scan` to get a list of devices addresses

You only need to install `python-bluez` or `python-bluetooth` package.

LICENSE LGPL <http://www.gnu.org/licenses/lgpl.html>
        (c) Nedim Jackman 2008 (c) Pierrick Koch 2016
"""
import sys
import time
import logging
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
N_SAMPLES               = 200
N_LOOP                  = 10

# initialize the logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler() # or RotatingFileHandler
handler.setFormatter(logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s] %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO) # or DEBUG

if len(sys.argv) > 1:
    address = sys.argv[1]
else:
    logger.info("Scan Bluetooth devices for 6 seconds...")
    devices = bluetooth.discover_devices(duration=6, lookup_names=True)
    logger.debug("Found devices: %s", str(devices))
    wiiboards = [address for address, name in devices \
                 if name == BLUETOOTH_NAME]
    logger.info("Found wiiboards: %s", str(wiiboards))
    if not wiiboards:
        raise Exception("Press the red sync button on the board")
    address = wiiboards[0]

controlsocket = bluetooth.BluetoothSocket(bluetooth.L2CAP)
receivesocket = bluetooth.BluetoothSocket(bluetooth.L2CAP)

logger.info("Connecting to %s", address)
#logger.debug("Services available: %s", bluetooth.find_service(address=address))
controlsocket.connect((address, 0x11))
receivesocket.connect((address, 0x13))

def send(*data):
    controlsocket.send(b'\x52'+b''.join(data))

def reporting(mode=CONTINUOUS_REPORTING, extension=EXTENSION_8BYTES):
    send(COMMAND_REPORTING, mode, extension)

def light(on_off=True):
    send(COMMAND_LIGHT, '\x10' if on_off else '\x00')

def status():
    send(COMMAND_REQUEST_STATUS, '\x00')

calibration = [[10000]*4]*3
logger.debug("Sending mass calibration request")
send(COMMAND_READ_REGISTER, "\x04\xA4\x00\x24\x00\x18")
calibration_requested = True
logger.info("Wait for calibration")
logger.debug("Connect to the balance extension, to read mass data")
send(COMMAND_REGISTER, "\x04\xA4\x00\x40\x00")
logger.debug("Request status")
status()
light(0)

b2i = lambda b: int(b.encode("hex"), 16)

def calc_mass(raw, pos):
    # Calculates the Kilogram weight reading from raw data at position pos
    # calibration[0] is calibration values for 0kg
    # calibration[1] is calibration values for 17kg
    # calibration[2] is calibration values for 34kg
    if raw < calibration[0][pos]:
        return 0.0
    elif raw < calibration[1][pos]:
        return 17 * ((raw - calibration[0][pos]) /
                     float((calibration[1][pos] - calibration[0][pos])))
    else: # if raw >= calibration[1][pos]:
        return 17 + 17 * ((raw - calibration[1][pos]) /
                          float((calibration[2][pos] - calibration[1][pos])))

def check_button(data, button_down=False):
    state = b2i(data)
    if state == BUTTON_DOWN_MASK:
        if not button_down:
            logger.info("Button pressed")
        return True
    elif button_down:
        logger.info("Button released")
    return False

def get_mass(data):
    return {
        'top_right':    calc_mass(b2i(data[0:2]), TOP_RIGHT),
        'bottom_right': calc_mass(b2i(data[2:4]), BOTTOM_RIGHT),
        'top_left':     calc_mass(b2i(data[4:6]), TOP_LEFT),
        'bottom_left':  calc_mass(b2i(data[6:8]), BOTTOM_LEFT),
    }

nloop = 0
samples = []
light_state = False
button_down = False
logger.debug("Starting the receive loop")
while receivesocket:
    data = receivesocket.recv(25)
    logger.debug("socket.recv(25): %r", data)
    if len(data) < 2:
        continue
    input_type = data[1]
    if input_type == INPUT_STATUS:
        reporting() # Must set the reporting type after every status report
        battery = b2i(data[7:9]) / BATTERY_MAX
        light_state = b2i(data[4]) & LED1_MASK == LED1_MASK
        logger.info("Status: battery: %.2f%% light: %s", battery*100.0,
                    'on' if light_state else 'off') # 0x12: on, 0x02: off/blink
        light(1)
    elif input_type == INPUT_READ_DATA:
        logger.debug("Got calibration data")
        if calibration_requested:
            length = b2i(data[4]) / 16 + 1
            data = data[7:7 + length]
            cal = lambda d: [b2i(d[j:j+2]) for j in [0, 2, 4, 6]]
            if length == 16: # First packet of calibration data
                calibration = [cal(data[0:8]), cal(data[8:16]), [10000]*4]
            elif length < 16: # Second packet of calibration data
                calibration[2] = cal(data[0:8])
                logger.info("Board calibrated: %s", str(calibration))
                calibration_requested = False
                light(1)
    elif input_type == EXTENSION_8BYTES:
        button_down = check_button(data[2:4], button_down)
        all_mass = get_mass(data[4:12])
        logger.debug("All mass: %s", str(all_mass))
        total = sum(all_mass.values())
        samples.append(total)
        if len(samples) > N_SAMPLES:
            print("%.3f %.3f"%(time.time(), sum(samples) / len(samples)))
            samples = []
            status() # Stop the board from publishing mass data
            nloop += 1
            if nloop > N_LOOP:
                break
            light(0)
            time.sleep(5)

# end
if receivesocket: receivesocket.close()
if controlsocket: controlsocket.close()
