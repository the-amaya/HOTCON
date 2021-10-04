# HOTCON
<p align="center">
	<img alt="GitHub language count" src="https://img.shields.io/github/languages/count/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub top language" src="https://img.shields.io/github/languages/top/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub code size in bytes" src="https://img.shields.io/github/languages/code-size/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub" src="https://img.shields.io/github/license/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub contributors" src="https://img.shields.io/github/contributors/the-amaya/HOTCON?style=plastic">
	<img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/the-amaya/HOTCON?style=plastic">
</p>
HOTtub CONtrol-system

This project is the hardware and software for my hottub.

#todo-
everything

#roadmap
1. hardware design
   1. AC-CTRL-BRD
   2. Upper-control-unit
   3. main-board
2. software design
   1. hotub hardware control and reading
      1. output control
         1. safe switching routines, build this as an object we call later to ensure universal behavior in code
      2. input handling
         1. probably build this as an individual object for each hardware input (thermometer, high-limit, flow switch)
   2. user interface
      1. output display (7 segmet display, button lights)
      2. user input handling (buttons)