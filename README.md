Wii Fit Balance Board (WBB) in python
=====================================

```
usage: wiiboard.py [address] 2> wiiboard.log > wiiboard.txt
tip: use `hcitool scan` to get a list of devices addresses
```

You only need to install `python-bluez` or `python-bluetooth` package.

Original version from Nedim Jackman in 2008 [based? on "wiibalancepc"]:
* https://code.google.com/archive/p/wiiboard-simple/
* http://trackingbalance.blogspot.fr/2008/08/small-milestone.html

Note to developers
------------------

wiiboard_simple_src_1.0.0.zip/WiiboardSimple/src/edu/unsw/cse/wiiboard/WiiBoard.java
The Wii Balance Board is very similar in most hardware properties of the wiimote.
The force sensing component is treated as an extension to a wiimote.
Most of the implementation details are sourced from the wiibrew project:
* http://wiibrew.org/wiki/Wii_Balance_Board
* http://web.archive.org/http://www.wiili.org/index.php/Wiimote

Changes from Nedim's version
----------------------------

* fix Wiiboard.calcMass where `raw == self.calibration[1][pos]` would return 0.0
* add INPUT_STATUS code to get battery level and light status
* store constants in byte to avoid unnecessary conversion
* skip device discovery when passing an address in argument
* add logging (to stderr)

Since then few other projects using Nedim's code:
* https://www.stavros.io/posts/your-weight-online/
* https://github.com/initialstate/beerfridge
* http://aelveborn.com/Wii-Scale/

Other wiimote interface / driver:
* https://github.com/abstrakraft/cwiid
* https://github.com/dvdhrm/xwiimote

Kernel bluetooth code (deal with the pairing key since 2012-09-21):
* https://git.kernel.org/cgit/bluetooth/bluez.git/tree/plugins/wiimote.c


TODO
----

Pressing the red sync button under the battery cover at each start-up is not
convinient. We should find a way with DBus to get a socket for paired bluetooth
input device, in which case one would only have to press the front power button.

```python
BLUEZ_VERSION = 5
try: # disconnect paired device with BlueZ API v5+
    logger.debug("bluez/test/test-device disconnect %s", address)
    import dbus
    bus = dbus.SystemBus()
    obj = bus.get_object("org.bluez", "/")
    if BLUEZ_VERSION >= 5:
        manager = dbus.Interface(obj, "org.freedesktop.DBus.ObjectManager")
        objects = manager.GetManagedObjects()
        for path, ifaces in objects.iteritems():
            device = ifaces.get("org.bluez.Device1")
            if device is not None and device.get("Address") == address:
                obj = bus.get_object("org.bluez", path)
                dev = dbus.Interface(obj, "org.bluez.Device1")
                # TODO check how can we get socket out of that
                # see bluez/test/test-profile
                logger.debug("  Disconnect %s", path)
                dev.Disconnect()
    else:
        manager = dbus.Interface(obj, "org.bluez.Manager")
        adapter_path = manager.DefaultAdapter()
        obj = bus.get_object("org.bluez", adapter_path)
        adapter = dbus.Interface(obj, "org.bluez.Adapter")
        device_path = adapter.FindDevice(address)
        obj = bus.get_object("org.bluez", device_path)
        device = dbus.Interface(obj, "org.bluez.Device") # or Input
        device.Disconnect()
except Exception as err:
    logger.warning("dbus failed: %s", str(err))
```

Threading
---------

*for threaded version use something like*

```python
import threading

class WiiboardThreaded(Wiiboard):
    def __init__(self, address=None):
        self.thread = threading.Thread(target=self.loop)
        Wiiboard.__init__(self, address)
    def connect(self, address):
        Wiiboard.connect(self, address)
        self.thread.start()
    def spin(self):
        while self.thread.is_alive():
            self.thread.join(1)
```

Center of mass
--------------

```python
def on_mass(self, mass):
    comx = 1.0
    comy = 1.0
    try:
        total_right  = mass['top_right']   + mass['bottom_right']
        total_left   = mass['top_left']    + mass['bottom_left']
        comx = total_right / total_left
        if comx > 1:
            comx = 1 - total_right / total_left
        else:
            comx -= 1
        total_bottom = mass['bottom_left'] + mass['bottom_right']
        total_top    = mass['top_left']    + mass['top_right']
        comy = total_bottom / total_top
        if comy > 1:
            comy = 1 - total_top / total_bottom
        else:
            comy -= 1
    except:
        pass
    print("Center of mass: %s"%str({'x': comx, 'y': comy}))
    # plot(x,y) using pygame or any other GUI
```
