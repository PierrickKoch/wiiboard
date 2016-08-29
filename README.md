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

Other wiimote interface / driver:
* https://github.com/abstrakraft/cwiid
* https://github.com/dvdhrm/xwiimote

Kernel bluetooth code (deal with the pairing key since 2012-09-21):
* https://git.kernel.org/cgit/bluetooth/bluez.git/tree/plugins/wiimote.c


TODO
----

play with DBus for paired bluetooth input device:

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
