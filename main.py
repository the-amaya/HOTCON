#!/usr/bin/env python3

import board
import busio
from adafruit_ht16k33.segments import Seg7x4
from digitalio import Direction
from adafruit_mcp230xx.mcp23017 import MCP23017
from time import sleep, localtime, strftime


# setup AC brd out
i2c20 = busio.I2C(board.SCL, board.SDA)
mcp = MCP23017(i2c20, address=0x20)

# setup display
i2c70 = board.I2C()
display = Seg7x4(i2c70)
display.brightness = 13/16


# TODO
# dictionary for output pin setup
# probably input pins as well


# display time
def distime():
    current_time = strftime("%H:%M", localtime())
    display.print(current_time)
    sleep(0.5)
    display.colon = False
    sleep(0.5)


def main():
    while True:
        distime()


def keyboardInterruptHandler(signal, frame):
    print("doing cleanup stuff here")
    display.fill(0) # blank the display
    # TODO
    # cleanup
    exit(0)


signal.signal(signal.SIGINT, keyboardInterruptHandler)


if __name__ == '__main__':
    main()
