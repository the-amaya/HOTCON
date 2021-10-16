from adafruit_ht16k33.segments import Seg7x4
from time import sleep, localtime, strftime

# setup display
i2c70 = board.I2C()
display = Seg7x4(i2c70)
display.brightness = 13/16


# display time
def distime() -> None:
    current_time = strftime("%H:%M", localtime())
    display.print(current_time)
    sleep(0.5)
    display.colon = False
    sleep(0.5)


def display_cleanup() -> None:
    display.fill(0)  # blank the display