import board
import busio
from digitalio import Direction
from adafruit_mcp230xx.mcp23017 import MCP23017
from time import sleep


# todo figure out the actual pins for these things
output_setup = {
    'pump1': 'mcp.get_pin(0)',
    'pump2': 'mcp.get_pin(0)',
    'pump1_speed': 'mcp.get_pin(0)',
    'pump2_speed': 'mcp.get_pin(0)',
    'circ_pump': 'mcp.get_pin(0)',
    'heater': 'mcp.get_pin(0)',
    'fan': 'mcp.get_pin(0)',
    'light': 'mcp.get_pin(0)',
    'ozone': 'mcp.get_pin(0)'
    }

# setup AC brd out
i2c20 = busio.I2C(board.SCL, board.SDA)
mcp = MCP23017(i2c20, address=0x20)


# setup all the output pins for tub control
for i in output_setup.items():
    i[0] = i[1]  # untested probably broken
    i[0].direction = Direction.OUTPUT


def pump_state_change(name: str, speed: int) -> None:
    psn = name + '_speed'
    if name.value == 1:  # if the pump is already on we need to turn it off before making speed changes
        name.value = False
        sleep(0.05)
        psn.value = False  # go ahead and switch to low speed with the pump off
    if speed == 1:  # low speed we just need to turn the pump (back) on
        sleep(0.05)
        name.value = True
    if speed == 2:  # high speed we first set the speed relay then turn the pump (back) on
        psn.value = True
        sleep(0.05)
        name.value = True


def circulation(speed: int) -> None:
    if speed == 0:
        if heater.value is True:  # if the heater is running it needs shut off before we can shut of the circ pump
            heater.value = False
            sleep(1)
        circ_pump.value = False
    if speed == 1:
        circ_pump.value = True


def heater(state: int) -> None:
    if state == 0:
        heater.value = False
    if state == 1:
        circulation(1)
        # TODO check flow sensor before allowing heater to turn on
        # TODO consider making the flow sensor a hardware interlock we can read
        heater.value = True
