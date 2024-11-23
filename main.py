import threading
import signal
import sys

from tub_api import start_api_server, handle_exit_api
from tub_control import start_tub_system, handle_exit_tub, send_discord_hook


def combined_exit_handler(signal_received, frame):
    message = 'exit handler received the following signal: ' + str(signal_received)
    send_discord_hook(message)
    handle_exit_api(signal_received, frame)
    handle_exit_tub(signal_received, frame)
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, combined_exit_handler)
    signal.signal(signal.SIGTERM, combined_exit_handler)

    threading.Thread(target=start_tub_system, daemon=True).start()
    start_api_server()
