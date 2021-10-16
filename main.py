#!/usr/bin/env python3
import signal
from display import distime, display_cleanup

def main():
    while True:
        distime()


def keyboardInterruptHandler(signal, frame):
    print("doing cleanup stuff here")
    display_cleanup()
    # TODO
    # cleanup
    exit(0)


signal.signal(signal.SIGINT, keyboardInterruptHandler)


if __name__ == '__main__':
    main()
