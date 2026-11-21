"""Interactive robot picker.

In a classroom the only robot in range may well be someone else's, so the CLI never connects
to a robot it wasn't explicitly told to use: it shows this list, even for a single robot.
Each robot's Bluetooth name (Makeblock_LE…) is printed on its side, so students can match it.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable

from .device import Found, RobotError, eprint, scan

HELP = (
    "Check the name printed on the side of YOUR robot. Type its number in the list, "
    "or the last few characters of its name. 'r' rescans, 'q' quits."
)


@dataclass(frozen=True)
class Choice:
    action: str  # pick | rescan | quit | invalid
    index: int = -1
    message: str = ""


def _norm(s: str) -> str:
    return s.lower().replace(":", "").replace("-", "").replace("_", "").replace(" ", "")


def parse_choice(text: str, robots: list[Found], last_used: str | None = None) -> Choice:
    t = text.strip()
    low = t.lower()
    if low in ("q", "quit", "exit"):
        return Choice("quit")
    if low in ("r", "rescan", "scan") or (not t and not robots):
        return Choice("rescan")
    if not t:
        # Enter reuses the robot this computer used last, but only if it's in range right now.
        for i, r in enumerate(robots):
            if last_used and r.address == last_used:
                return Choice("pick", i)
        return Choice("invalid", message="Type a number from the list or part of your robot's name.")
    if t.isdigit() and len(t) <= 2:
        n = int(t)
        if 1 <= n <= len(robots):
            return Choice("pick", n - 1)
        return Choice("invalid", message=f"Pick a number from 1 to {len(robots)}." if robots else "No robots to pick.")
    frag = _norm(t)
    hits = [i for i, r in enumerate(robots) if frag in _norm(r.name) or frag in _norm(r.address)]
    if len(hits) == 1:
        return Choice("pick", hits[0])
    if not hits:
        return Choice("invalid", message=f"No robot in the list matches '{t}'. Is yours switched on? ('r' rescans)")
    return Choice("invalid", message=f"'{t}' matches {len(hits)} robots; type more of the name, or its number.")


def signal_bars(rssi: int) -> str:
    level = 4 if rssi >= -55 else 3 if rssi >= -67 else 2 if rssi >= -78 else 1
    return "#" * level + "." * (4 - level)


def format_list(robots: list[Found], last_used: str | None) -> str:
    lines = []
    for i, r in enumerate(robots, 1):
        tag = "   <- last used on this computer" if r.address == last_used else ""
        lines.append(f"  {i}) {r.name:<26} signal {signal_bars(r.rssi)}  {r.address}{tag}")
    return "\n".join(lines)


async def _ask(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def pick_robot(
    last_used: str | None,
    ask: Callable[[str], Awaitable[str]] = _ask,
    find: Callable[[], Awaitable[list[Found]]] = lambda: scan(5.0),
) -> Found:
    """Scan, show the list, and return the robot the user explicitly chose."""
    robots: list[Found] = []
    rescan = True
    while True:
        if rescan:
            eprint("Scanning for robots...")
            robots = await find()
            rescan = False
            if robots:
                eprint(f"Found {len(robots)} robot{'s' if len(robots) != 1 else ''}:")
                eprint(format_list(robots, last_used))
                eprint(HELP)
                last = next((r for r in robots if r.address == last_used), None)
                if last:
                    eprint(f"Press Enter to use {last.name} again (last used on this computer).")
            else:
                eprint("No robots found. Is yours switched on (battery switch) and not connected to mBlock?")
                eprint("Press Enter to scan again, 'q' to quit.")
        try:
            answer = await ask("Your robot: ")
        except EOFError:
            raise RobotError("No robot chosen.")
        c = parse_choice(answer, robots, last_used)
        if c.action == "quit":
            raise RobotError("No robot chosen.")
        if c.action == "rescan":
            rescan = True
        elif c.action == "invalid":
            eprint(c.message)
        else:
            return robots[c.index]


def can_prompt() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()
