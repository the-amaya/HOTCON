import sys
import os
import time
import logging
import signal
import sched
import asyncio
import threading
from typing import List, Tuple
from multiprocessing import Manager
import board
import busio
import digitalio
from adafruit_mcp230xx.mcp23017 import MCP23017
from datetime import datetime, timedelta
import requests
import json

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the I2C bus
i2c = busio.I2C(board.SCL, board.SDA)
mcp = MCP23017(i2c, address=0x20)  # MCP23017 w/ A0 set

# Globally set the directory where the sensor data resides
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')
base_dir = '/sys/bus/w1/devices/'

# set up the discord webhook
DISCORD_WEBHOOK_URL = ""

# Initialize scheduler
scheduler = sched.scheduler(time.time, time.sleep)


# Function to handle fatal errors and cleanup before exiting
def fatal_error(message):
    cs.cleanup()
    send_discord_hook(message)
    logger.critical(message)


def send_discord_hook(message):
    if DISCORD_WEBHOOK_URL != '':
        data = {"content": message}
        response = requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(data), headers={"Content-Type": "application/json"})
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            print(f"HTTPError: {err}")


def schedule_task_at(hour: int, minute: int, func, *args):
    now = datetime.now()
    target_time = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=hour, minutes=minute)
    if target_time < now:
        target_time += timedelta(days=1)  # Schedule for the next day if the target time already passed today
    delay = (target_time - now).total_seconds()
    scheduler.enter(delay, 1, func, args)
    return target_time


class Heater:
    def __init__(self):
        self.name = 'heater'
        self.pin = mcp.get_pin(7)
        self.pin.switch_to_output(value=False)
        self.internal_state = False
        self.last_change_time = time.time()

    def set_state(self, new_state: bool) -> None:
        circ_pump_runtime = time.time() - cs.circpump.last_change_time
        lockout_timer = time.time() - self.last_change_time
        if new_state and not cs.circpump.get_state():
            logger.info("Circ pump is not running. Make sure the circ pump runs at least 60 seconds before turning "
                        "the heater on. aborting.")
        elif new_state and circ_pump_runtime < 60:
            logger.info("Circ pump has not been running for at least 60 seconds. aborting heating.")
        elif new_state and lockout_timer < 60:
            logger.info(f"lockout timer is at {lockout_timer}. aborting heating to prevent the heater "
                        "short cycling.")
        else:
            self.pin.value = new_state
            self.internal_state = new_state
            self.last_change_time = time.time()
            logger.info(f"Heater state set to {new_state}")

    def get_state(self) -> bool:
        return self.internal_state

    def toggle_state(self) -> None:
        self.set_state(not self.get_state())

    def cleanup(self) -> None:
        self.set_state(False)


class Circ_Pump:
    def __init__(self):
        self.name = 'circpump'
        self.pin = mcp.get_pin(2)
        self.pin.switch_to_output(value=False)
        self.internal_state = False
        self.last_change_time = time.time()

    def set_state(self, new_state: bool) -> None:
        if not new_state and cs.heater.get_state():
            # heater is on, we need to shut it off
            cs.heater.set_state(False)
            time.sleep(5)
        self.pin.value = new_state
        self.internal_state = new_state
        self.last_change_time = time.time()
        logger.info(f"Circulation pump state set to {new_state}")

    def get_state(self) -> bool:
        return self.internal_state

    def toggle_state(self) -> None:
        self.set_state(not self.get_state())

    def cleanup(self) -> None:
        self.set_state(False)


class Main_Pump:
    def __init__(self, name: str, high_speed_pin: int, low_speed_pin: int):
        self.name = name
        self.high_speed_pin = mcp.get_pin(high_speed_pin)
        self.high_speed_pin.switch_to_output(value=False)
        self.low_speed_pin = mcp.get_pin(low_speed_pin)
        self.low_speed_pin.switch_to_output(value=False)
        self.internal_state = 'off'
        self.timer = None
        self.filter_cycle_timer = None
        self.last_change_time = time.time()
        if self.name == 'pump1':
            next_time = schedule_task_at(3, 0, self.auto_filter_cycle)
            logger.info(f"{self.name} next filter cycle scheduled at {next_time}")

    def set_state(self, new_state: bool, new_speed: str = 'low') -> None:
        if not new_state:
            self.low_speed_pin.value = False
            self.high_speed_pin.value = False
            self.internal_state = 'off'
        elif new_state and new_speed == 'low':
            if self.high_speed_pin.value:
                self.high_speed_pin.value = False
                time.sleep(0.1)
            self.low_speed_pin.value = True
            self.internal_state = 'low'
        elif new_state and new_speed == 'high':
            if not (self.low_speed_pin.value or self.high_speed_pin.value):
                self.low_speed_pin.value = True
                time.sleep(1)
            if self.low_speed_pin.value:
                self.low_speed_pin.value = False
                time.sleep(0.1)
            self.high_speed_pin.value = True
            self.internal_state = 'high'
        self.reset_timer()
        self.last_change_time = time.time()
        if new_state:
            logger.info(f"Main pump {self.name} state set to {new_state} with speed {new_speed}")
        else:
            logger.info(f"Main pump {self.name} state set to {new_state}")

    def advance_state(self) -> None:
        if not self.high_speed_pin.value and not self.low_speed_pin.value:
            self.low_speed_pin.value = True
            self.internal_state = 'low'
        elif self.low_speed_pin.value:
            self.low_speed_pin.value = False
            time.sleep(0.1)
            self.high_speed_pin.value = True
            self.internal_state = 'high'
        else:
            self.high_speed_pin.value = False
            self.internal_state = 'off'
        self.reset_timer()
        self.last_change_time = time.time()
        logger.info(f"Main pump {self.name} state advanced")

    def reset_timer(self) -> None:
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(20 * 60, self.auto_turn_off)
        self.timer.start()

    def auto_turn_off(self) -> None:
        if self.high_speed_pin.value or self.low_speed_pin.value:
            self.set_state(False)
            logger.info(f"Main pump {self.name} auto turned off")

    def auto_filter_cycle(self) -> None:
        if not self.high_speed_pin.value and not self.low_speed_pin.value:
            if time.time() - self.last_change_time > 60 * 60:
                self.set_state(True, 'high')
                logger.info(f"Main pump {self.name} auto filter cycle activated")
        # Schedule the next filter cycle at 3 AM
        next_time = schedule_task_at(3, 0, self.auto_filter_cycle)
        logger.info(f"Next filter cycle scheduled at {next_time}")

    def get_state(self) -> str:
        return self.internal_state

    def cleanup(self) -> None:
        self.set_state(False)
        if self.timer:
            self.timer.cancel()
        if self.filter_cycle_timer:
            self.filter_cycle_timer.cancel()


class Blower:
    def __init__(self):
        self.name = 'blower'
        self.pin = mcp.get_pin(1)
        self.pin.switch_to_output(value=False)
        self.internal_state = False
        self.last_change_time = time.time()

    def set_state(self, new_state: bool) -> None:
        self.pin.value = new_state
        self.internal_state = new_state
        self.last_change_time = time.time()
        logger.info(f"Blower state set to {new_state}")

    def get_state(self) -> bool:
        return self.internal_state

    def toggle_state(self) -> None:
        self.set_state(not self.get_state())

    def cleanup(self) -> None:
        self.set_state(False)


class Fans:
    def __init__(self):
        self.name = 'fans'
        self.pin = mcp.get_pin(10)
        self.pin.switch_to_output(value=False)
        self.internal_state = False
        self.last_change_time = time.time()

    def set_state(self, new_state: bool) -> None:
        self.pin.value = new_state
        self.internal_state = new_state
        self.last_change_time = time.time()
        logger.info(f"Fans state set to {new_state}")

    def get_state(self) -> bool:
        return self.internal_state

    def toggle_state(self) -> None:
        self.set_state(not self.get_state())

    def cleanup(self) -> None:
        self.set_state(False)


class Light:
    def __init__(self):
        self.name = 'light'
        self.pin = mcp.get_pin(0)
        self.pin.switch_to_output(value=False)
        self.internal_state = False
        self.timer = None
        self.last_change_time = time.time()

    def set_state(self, new_state: bool) -> None:
        self.pin.value = new_state
        self.internal_state = new_state
        self.last_change_time = time.time()
        self.reset_timer()
        logger.info(f"Light state set to {new_state}")

    def get_state(self) -> bool:
        return self.internal_state

    def toggle_state(self) -> None:
        self.set_state(not self.get_state())
        self.reset_timer()

    def reset_timer(self) -> None:
        if self.timer:
            self.timer.cancel()
        if self.pin.value:
            self.timer = threading.Timer(60 * 60, self.auto_turn_off)
            self.timer.start()

    def auto_turn_off(self) -> None:
        if self.pin.value:
            self.set_state(False)
            logger.info(f"Light auto turned off after 1 hour")

    def cleanup(self) -> None:
        self.set_state(False)
        if self.timer:
            self.timer.cancel()


class Ozone:
    def __init__(self):
        self.name = 'ozone'
        self.pin = mcp.get_pin(9)
        self.pin.switch_to_output(value=False)
        self.internal_state = False
        self.timer = None
        self.schedule_timer = None
        self.last_change_time = time.time()
        # Schedule the ozone run for 2 AM
        next_time = schedule_task_at(2, 0, self.run_ozone)
        logger.info(f"Next ozone run scheduled at {next_time}")

    def set_state(self, new_state: bool) -> None:
        circ_pump_runtime = time.time() - cs.circpump.last_change_time
        if new_state and not cs.circpump.get_state():
            logger.info("Circ pump is not running. Make sure the circ pump runs at least 30 seconds before turning "
                        "the ozone on. aborting.")
        elif new_state and circ_pump_runtime < 30:
            cs.circpump.set_state(True)
            logger.info("Circ pump has not been running for at least 30 seconds. Turning the circ pump on but "
                        "aborting this time.")
        else:
            self.pin.value = new_state
            self.internal_state = new_state
            self.last_change_time = time.time()
            logger.info(f"Ozone generator state set to {new_state}")
        if new_state:
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(60 * 60, self.auto_turn_off)
            self.timer.start()

    def auto_turn_off(self) -> None:
        if self.pin.value:
            self.set_state(False)
            logger.info(f"Ozone generator auto turned off after 1 hour")

    def run_ozone(self) -> None:
        self.set_state(True)
        # Schedule the next ozone run at 2 AM
        next_time = schedule_task_at(2, 0, self.run_ozone)
        logger.info(f"Next ozone run scheduled at {next_time}")

    def get_state(self) -> bool:
        return self.internal_state

    def toggle_state(self) -> None:
        self.set_state(not self.get_state())

    def cleanup(self) -> None:
        self.set_state(False)
        if self.timer:
            self.timer.cancel()
        if self.schedule_timer:
            self.schedule_timer.cancel()


class FlowSwitch:
    def __init__(self):
        self.flow = mcp.get_pin(8)
        self.flow.direction = digitalio.Direction.INPUT
        self.flow.pull = digitalio.Pull.UP

    def check_flow(self) -> bool:
        return not self.flow.value


class TemperatureSensor:
    def __init__(self, name: str, sensor_id: str):
        self.sensor_id = sensor_id
        self.name = name
        self.device_folder = base_dir + sensor_id + '/w1_slave'
        self.temperature_c = None
        self.temperature_f = None
        self.last_read_time = 0
        self.read_temp()

    def read_temp_raw(self) -> List[str]:
        try:
            time.sleep(1)
            with open(self.device_folder, 'r') as file:
                return file.readlines()
        except IOError as e:
            send_discord_hook(f"Error reading temperature sensor {self.name}: {e}")
            fatal_error(f"Error reading temperature sensor {self.name}: {e}")

    def read_temp(self) -> Tuple[float, float]:
        current_time = time.time()
        lines = self.read_temp_raw()
        while lines and lines[0].strip()[-3:] != 'YES':
            lines = self.read_temp_raw()
        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            try:
                temp_string = lines[1][equals_pos + 2:]
                temp_c = float(temp_string) / 1000.0
                temp_f = (temp_c * 1.8) + 32
                self.temperature_c, self.temperature_f = round(temp_c, 2), round(temp_f, 2)
                self.last_read_time = current_time
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing temperature sensor data: {e}")
        return self.temperature_c, self.temperature_f

    def f(self) -> float:
        return self.temperature_f

    def c(self) -> float:
        return self.temperature_c

    def cache_f(self) -> float:
        return self.temperature_f


class ComponentSystem:
    def __init__(self):
        self.heater = Heater()
        self.pump1 = Main_Pump('pump1', 6, 4)
        self.pump2 = Main_Pump('pump2', 5, 3)
        self.circpump = Circ_Pump()
        self.blower = Blower()
        self.fans = Fans()
        self.light = Light()
        self.flow = FlowSwitch()
        self.ozone = Ozone()
        self.temp_water = TemperatureSensor("water", "") # the second value is the 1-wire sensor address/id e.g. 28-000000000000
        self.temp_heater1 = TemperatureSensor("heater1", "")
        self.temp_heater2 = TemperatureSensor("heater2", "")
        self.temp_ambient = TemperatureSensor("ambient", "")
        self.temp_cabinet = TemperatureSensor("cabinet", "")
        self.temp_control_box = TemperatureSensor("control_box", "")
        self.set_temperature = 99.0  # Default temperature in Fahrenheit
        self.mode = 'automatic'  # Default mode is automatic
        self.start_time = time.time()
        self.loop_time = time.time()
        self.temp_sensor_update_timer = time.time()
        self.temp_sensor_round_robin = 0
        self.sensor_read = False

    def automatic_heater_logic(self) -> None:
        water_temp = self.temp_water.f()
        # TODO logic for water temp offset based on how long the main pumps have been off
        # need to collect temp data to know how to calculate this
        if water_temp < self.set_temperature and not self.circpump.get_state():
            logger.info('Turned circ pump on to heat')
            self.circpump.set_state(True)
        if self.flow.check_flow() and self.circpump.get_state():
            if water_temp < self.set_temperature - 1 and not self.heater.get_state():
                circ_pump_runtime = time.time() - self.circpump.last_change_time
                if circ_pump_runtime >= 60:
                    logger.info('Circ pump is running, flow switch active, turning heater on')
                    self.heater.set_state(True)
            elif water_temp > self.set_temperature and self.heater.get_state():
                logger.info('Water up to temp, turning heater off')
                self.heater.set_state(False)
        elif self.heater.get_state():
            self.heater.set_state(False)

    def automatic_blower_logic(self) -> None:
        cabinet_temp = self.temp_cabinet.f()
        control_box_temp = self.temp_control_box.f()
        water_temp = self.temp_water.f()
        pump1_runtime = time.time() - self.pump1.last_change_time
        pump2_runtime = time.time() - self.pump2.last_change_time
        if cabinet_temp > 90 or control_box_temp > 100:
            if not self.blower.get_state():
                logger.info('temperature condition met: turning blower on')
                self.blower.set_state(True)
        elif pump1_runtime >= 30 and self.pump1.get_state() != 'off':
            if not self.blower.get_state():
                logger.info('pump1 is running: turning blower on')
                self.blower.set_state(True)
        elif pump2_runtime >= 30 and self.pump2.get_state() != 'off':
            if not self.blower.get_state():
                logger.info('pump2 is running: turning blower on')
                self.blower.set_state(True)
        elif self.ozone.get_state():
            if not self.blower.get_state():
                logger.info('ozone is running: turning blower on')
                self.blower.set_state(True)
        elif water_temp > self.set_temperature + 3:
            if not self.blower.get_state():
                logger.info('water temp is too high, turning blower on')
                self.blower.set_state(True)
        elif cabinet_temp < 80 and control_box_temp < 90 and water_temp < self.set_temperature + 2:
            if self.blower.get_state():
                logger.info('Conditions not met: turning blower off')
                self.blower.set_state(False)
        else:
            # nothing to do here
            pass

    def automatic_fans_logic(self) -> None:
        cabinet_temp = self.temp_cabinet.f()
        control_box_temp = self.temp_control_box.f()
        if cabinet_temp > 85 or control_box_temp > 90:
            if not self.fans.get_state():
                logger.info('temperature condition met: turning fans on')
                self.fans.set_state(True)
        elif self.ozone.get_state():
            if not self.fans.get_state():
                logger.info('ozone is running: turning fans on')
                self.fans.set_state(True)
        elif cabinet_temp < 80 and control_box_temp < 80:
            if self.fans.get_state():
                logger.info('Conditions not met: turning fans off')
                self.fans.set_state(False)
        else:
            # nothing to do here
            pass

    def temp_sensor_update(self) -> None:
        if time.time() - self.temp_sensor_update_timer > 1:
            self.sensor_read = True
            temp_sensors = [
                self.temp_water, self.temp_heater1, self.temp_heater2,
                self.temp_cabinet, self.temp_control_box, self.temp_ambient
            ]
            print(f'reading sensor {temp_sensors[self.temp_sensor_round_robin].name}')
            temp_sensors[self.temp_sensor_round_robin].read_temp()
            self.temp_sensor_round_robin += 1
            if self.temp_sensor_round_robin == len(temp_sensors):
                self.temp_sensor_round_robin = 0
            self.temp_sensor_update_timer = time.time()
            self.sensor_read = False

    def freeze_protection(self) -> None:
        if self.temp_ambient.f() < 25:
            if not self.pump1.get_state():
                if time.time() - self.pump1.last_change_time > 21600:
                    self.pump1.set_state(True, 'low')
            if not self.pump2.get_state():
                if time.time() - self.pump2.last_change_time > 21600:
                    self.pump2.set_state(True, 'low')

    def heater_high_limit_check(self) -> None:
        if self.temp_heater1.f() > 150 or self.temp_heater2.f() > 150:
            self.heater.set_state(False)
            logger.warning("Emergency: Heater temperature too high!")

    def flow_check(self) -> None:
        if self.heater.get_state() and not self.flow.check_flow():
            self.heater.set_state(False)
            logger.warning("Emergency: No Flow detected while heater running!")

    def get_state(self) -> dict:
        temp_sensors = [
            self.temp_water, self.temp_heater1, self.temp_heater2,
            self.temp_cabinet, self.temp_control_box, self.temp_ambient
        ]
        devices = [self.heater, self.circpump, self.blower, self.fans, self.light, self.ozone]
        pumps = [self.pump1, self.pump2]
        return {
            'set_temperature': self.set_temperature,
            'mode': self.mode,
            'temperatures': {sensor.name: sensor.cache_f() for sensor in temp_sensors},
            'devices': {
                device.name: {
                    'state': device.get_state(),
                    'last_change_time': round(time.time() - device.last_change_time),
                } for device in devices
            },
            'main_pumps': {
                pump.name: {
                    'state': pump.get_state(),
                    'last_change_time': round(time.time() - pump.last_change_time),
                } for pump in pumps
            },
            'flow_switch': self.flow.check_flow(),
            'start_time': self.start_time,
            'loop_time': round(time.time() - self.loop_time),
            'current_time': time.time(),
            'sensor_read': self.sensor_read
        }

    def cleanup(self) -> None:
        logger.info("Shutting down all components...")
        for comp in [self.heater, self.pump1, self.pump2, self.circpump, self.blower, self.fans, self.light,
                     self.ozone]:
            comp.cleanup()


cs = ComponentSystem()


async def tub_loop():
    while True:
        scheduler.run(blocking=False)  # Run scheduled tasks
        cs.temp_sensor_update()
        if cs.mode == 'automatic':
            cs.automatic_heater_logic()
            cs.automatic_blower_logic()
            cs.automatic_fans_logic()
            cs.freeze_protection()
        cs.heater_high_limit_check()
        cs.flow_check()
        cs.loop_time = time.time()
        await asyncio.sleep(0.2)


def handle_exit_tub(*args) -> None:
    logger.info("Received shutdown signal, performing hardware cleanup.")
    cs.cleanup()
    logger.info("Cleanup completed. Exiting now.")
    send_discord_hook("Received shutdown signal, performing hardware cleanup.")


def start_tub_system():
    send_discord_hook('hottub started')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(tub_loop())
    loop.run_forever()


if __name__ == "__main__":
    try:
        start_tub_system()
    except (KeyboardInterrupt, SystemExit):
        handle_exit_tub()
