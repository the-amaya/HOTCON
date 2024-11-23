# HOTCON
<p align="center">
	<img alt="GitHub language count" src="https://img.shields.io/github/languages/count/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub top language" src="https://img.shields.io/github/languages/top/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub code size in bytes" src="https://img.shields.io/github/languages/code-size/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub" src="https://img.shields.io/github/license/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub contributors" src="https://img.shields.io/github/contributors/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/the-amaya/HOTCON?style=plastic">
</p>
HOTtub CONtrol system

This project is the hardware and software for my hottub. Current features include hardware control, automated tub control logic including heating control and filter cycles.

NOTICE: use this at your own risk. if you break your hot tub or set it on fire or anything else I am not responsible. I have taken steps to ensure this software is fail-safe but controlling a heater purely in software is inherently dangerous.

# Usage

`python main.py`

Currently I have not implemented buttons or a display on the tub for control. This software provides a web app and API for tub control.

The main web interface is available at 127.0.0.1:8000
the admin control panel is at 127.0.0.1:8000/admin
and API documentation is available at 127.0.0.1:8000/docs

In tub_control.py you need to set the ID for the temperature sensors on lines 432-437.
In index.html and admin.html you need to set the IP or URL for your hottub. (lines 138-139 for index.html and 236-237 for admin.html)

# Hardware

need to document the hardware and put together a BOM.

The heart of the project is a raspberry pi 4. using a number of support components I built a custom control board to interface with the tub hardware. The heater and main pumps use 2-pole contactors and everything else uses single pole relays.

Currently implemented hardware features:
- Main jet pumps
- circulator pump
- heater
- light
- fan
- blower
- ozone generator

Still to come hardware features:
- upper controls for the tub (buttons and a 7-segment display is planned)