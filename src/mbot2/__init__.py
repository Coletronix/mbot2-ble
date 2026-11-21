"""Upload MicroPython programs to a Makeblock mBot2 / CyberPi over Bluetooth LE."""


def main() -> int:
    from .cli import main as _main

    return _main()
