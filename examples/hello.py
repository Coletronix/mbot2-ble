# Hello from mbot2-cli: green LEDs, a label on screen, and a heartbeat on stdout.
import time

import cyberpi
import event


@event.start
def on_start():
    cyberpi.led.on(0, 255, 0)
    cyberpi.display.clear()
    cyberpi.display.show_label("Hello BLE!", 16, "center")
    n = 0
    while True:
        print("heartbeat", n)
        n += 1
        time.sleep(1)
