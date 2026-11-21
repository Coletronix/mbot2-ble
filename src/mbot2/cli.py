"""mbot2: upload MicroPython programs to a Makeblock mBot2 / CyberPi over Bluetooth LE."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

from bleak.exc import BleakError

from . import protocol as P
from .device import Found, Robot, RobotError, eprint, scan
from .picker import can_prompt, format_list, pick_robot

def _config_dir() -> Path:
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "mbot2"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mbot2"


CONFIG = _config_dir() / "config.json"


# ------------------------------------------------------------------ config
def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(**kw) -> None:
    cfg = load_config() | kw
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


async def target_of(args):
    """The robot to talk to. Never guesses: without -d/$MBOT2_DEVICE the user picks from a
    list, even when only one robot is in range (it may be a classmate's). --auto skips the
    list only when exactly one robot is in range."""
    if getattr(args, "_device", None) is not None:  # first connection after picking: no rescan
        dev, args._device = args._device, None
        return dev
    if getattr(args, "_target", None):
        return args._target
    explicit = args.device or os.environ.get("MBOT2_DEVICE")
    if explicit:
        args._target = explicit
        return explicit
    last_used = load_config().get("device")
    chosen: Found | None = None
    if args.auto or os.environ.get("MBOT2_AUTO", "0") != "0":
        robots = await scan(5.0)
        if len(robots) == 1:
            chosen = robots[0]
            eprint(f"--auto: using the only robot in range, {chosen.name} ({chosen.address}).")
        elif not robots:
            raise RobotError("--auto: no robots in range. Is yours switched on (battery switch)?")
        else:
            eprint(f"--auto: {len(robots)} robots in range, so you need to choose.")
    if chosen is None:
        if not can_prompt():
            raise RobotError(
                "Which robot? Not running in an interactive terminal, so I can't ask. "
                "Pass -d ADDRESS (see `mbot2 scan`), set MBOT2_DEVICE, or use --auto."
            )
        chosen = await pick_robot(last_used)
        eprint(f"Tip: next time, skip this list with  -d {chosen.address}")
    args._target = chosen.address
    return chosen.device


# ------------------------------------------------------------------ output
class Console:
    """Prints program output from the robot, keeping partial lines together."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet

    def text(self, b: bytes) -> None:
        if not self.quiet:
            sys.stdout.write(b.decode("utf-8", "replace").replace("\r\n", "\n"))
            sys.stdout.flush()


def progress_bar(done: int, total: int) -> None:
    if not sys.stderr.isatty():
        return
    w = 30
    fill = int(w * done / total)
    sys.stderr.write(f"\r  [{'#' * fill}{'.' * (w - fill)}] {done}/{total} frames")
    if done == total:
        sys.stderr.write("\n")
    sys.stderr.flush()


# ------------------------------------------------------------------ checks
def read_source(path: Path) -> bytes:
    src = path.read_bytes()
    if src.startswith(b"\xef\xbb\xbf"):  # UTF-8 BOM (e.g. Windows Notepad): MicroPython chokes on it
        src = src[3:]
    return src


ENTRY_RE = re.compile(r"^\s*@\s*event\.\w+", re.M)


def check_source(src: bytes, path: Path) -> list[str]:
    problems = []
    try:
        text = src.decode("utf-8")
    except UnicodeDecodeError:
        return ["file is not valid UTF-8"]
    try:
        compile(text, str(path), "exec")
    except SyntaxError as e:
        problems.append(f"syntax error: line {e.lineno}: {e.msg}")
    if not ENTRY_RE.search(text):
        problems.append(
            "no @event.start (or other @event.*) handler found. The CyberPi firmware runs uploaded programs "
            "through its event system; top-level-only programs have been reported to hang the board at boot."
        )
    return problems


# ------------------------------------------------------------------ commands
async def cmd_scan(args) -> int:
    robots = await scan(args.timeout)
    if not robots:
        eprint("No Makeblock robots found.")
        return 1
    print(format_list(robots, load_config().get("device")))
    return 0



async def cmd_upload(args) -> int:
    path = Path(args.file)
    src = read_source(path)
    problems = check_source(src, path)
    if problems and not args.force:
        for p in problems:
            eprint(f"error: {path}: {p}")
        eprint("Refusing to upload (use --force to upload anyway).")
        return 2
    for p in problems:
        eprint(f"warning: {path}: {p}")

    con = Console(quiet=True)
    async with Robot(await target_of(args), on_text=con.text, log=eprint) as robot:
        t0 = time.monotonic()
        save_config(device=robot.address)
        eprint(f"Uploading {path.name} ({len(src)} bytes) as '{args.name}'...")
        sent = await robot.upload(src, args.name, progress_bar)
        eprint(f"Uploaded {sent} bytes in {time.monotonic() - t0:.1f}s.")
        if args.no_reset:
            eprint("Not restarting (--no-reset). The new program runs after the next power cycle.")
            return 0
        # The firmware normally restarts by itself right after the upload ("PYB: fast reboot").
        if robot.rebooting.is_set() or await robot.wait_for_reboot(4.0):
            eprint("Robot restarted; the new program is running.")
        else:
            eprint("Restarting the robot...")
            if await robot.reboot():
                eprint("Robot restarted; the new program is running.")
            else:
                eprint("warning: no restart seen; power-cycle the robot if the old program is still running.")
    if args.monitor:
        return await monitor(args, reconnect_wait=2.0)
    eprint("Done.")
    return 0


async def monitor(args, reconnect_wait: float = 0.0) -> int:
    """Show the program's print() output (stdout is mirrored over BLE). Ctrl-C to quit."""
    con = Console()
    if not getattr(args, "_target", None):  # choose once, up front; reconnects reuse the choice
        args._device = await target_of(args)
    eprint("Monitoring robot output (Ctrl-C to stop).")
    while True:
        if reconnect_wait:
            await asyncio.sleep(reconnect_wait)
        try:
            async with Robot(await target_of(args), on_text=con.text, log=eprint) as robot:
                save_config(device=robot.address)
                await robot.enable_print()
                await robot.disconnected.wait()
                eprint("\n[disconnected: robot restarted or went out of range; reconnecting]")
        except RobotError as e:
            eprint(f"[{e}]")
        except Exception as e:  # BLE stacks throw all sorts of things during a reboot
            eprint(f"[connection error: {e}; retrying]")
        reconnect_wait = 2.0


async def cmd_monitor(args) -> int:
    return await monitor(args)


async def cmd_eval(args) -> int:
    async with Robot(await target_of(args), log=lambda s: None) as robot:
        save_config(device=robot.address)
        result = await robot.eval(args.expr, timeout=args.timeout)
    print(json.dumps(result) if not isinstance(result, str) else result)
    return 0


async def cmd_exec(args) -> int:
    code = Path(args.file).read_text() if args.file else args.code
    async with Robot(await target_of(args), on_text=Console().text, log=lambda s: None) as robot:
        save_config(device=robot.address)
        await robot.enable_print()
        await robot.exec(code)
        await asyncio.sleep(args.wait)
    return 0


async def cmd_reset(args) -> int:
    async with Robot(await target_of(args), log=eprint) as robot:
        ok = await robot.reboot()
    eprint("Restarted." if ok else "No restart seen.")
    return 0 if ok else 1


async def cmd_forget(args) -> int:
    save_config(device=None)
    eprint("Forgot the last-used robot (it's no longer marked in the picker).")
    return 0


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mbot2",
        description="Upload MicroPython programs to a Makeblock mBot2 / CyberPi over Bluetooth LE.",
    )
    p.add_argument(
        "-d", "--device",
        help="robot address or name fragment; skips the robot picker (default: $MBOT2_DEVICE, else ask)",
    )
    p.add_argument(
        "-a", "--auto", action="store_true",
        help="if exactly one robot is in range, use it without asking ($MBOT2_AUTO=1 does the same). "
        "Careful in classrooms: the only robot in range may not be yours",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true",
        help="log connection settings and every Bluetooth packet (for bug reports)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="list Makeblock robots nearby")
    s.add_argument("-t", "--timeout", type=float, default=5.0)
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("upload", aliases=["up"], help="upload a .py file as the robot's program and run it")
    s.add_argument("file")
    s.add_argument("-n", "--name", default="main", help="program slot name (default: main)")
    s.add_argument("-m", "--monitor", action="store_true", help="show the program's print() output afterwards")
    s.add_argument("--no-reset", action="store_true", help="don't restart the robot after uploading")
    s.add_argument("-f", "--force", action="store_true", help="upload even if the pre-upload checks fail")
    s.set_defaults(func=cmd_upload)

    s = sub.add_parser("monitor", aliases=["mon"], help="show the running program's print() output")
    s.set_defaults(func=cmd_monitor)

    s = sub.add_parser("eval", help="evaluate a Python expression on the robot and print the result")
    s.add_argument("expr")
    s.add_argument("-t", "--timeout", type=float, default=3.0)
    s.set_defaults(func=cmd_eval)

    s = sub.add_parser("exec", help="run a snippet of Python on the robot (no result)")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("code", nargs="?")
    g.add_argument("--file")
    s.add_argument("-w", "--wait", type=float, default=1.0, help="seconds to show output afterwards")
    s.set_defaults(func=cmd_exec)

    s = sub.add_parser("reset", aliases=["reboot"], help="restart the robot")
    s.set_defaults(func=cmd_reset)

    s = sub.add_parser("forget", help="forget the last-used robot")
    s.set_defaults(func=cmd_forget)
    return p


def _safe_streams() -> None:
    """Never crash on robot output the console can't encode (e.g. cp1252 consoles/pipes on Windows)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _safe_streams()
    args = build_parser().parse_args(argv)
    if args.verbose:
        os.environ["MBOT2_DEBUG"] = "1"
    try:
        return asyncio.run(args.func(args))
    except KeyboardInterrupt:
        return 130
    except (RobotError, FileNotFoundError) as e:
        eprint(f"error: {e}")
        return 1
    except BleakError as e:
        eprint(f"error: Bluetooth: {e}")
        return 1
