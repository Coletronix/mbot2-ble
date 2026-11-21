"""BLE connection to a CyberPi / mBot2 and the upload sequence."""

from __future__ import annotations

import asyncio
import os
import sys
import time
import warnings
from dataclasses import dataclass
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import protocol as P

SERVICE = "0000ffe1-0000-1000-8000-00805f9b34fb"
WRITE = "0000ffe3-0000-1000-8000-00805f9b34fb"
NOTIFY = "0000ffe2-0000-1000-8000-00805f9b34fb"
NAME_PREFIX = "Makeblock"
# The robot's write characteristic accepts at most 64 bytes per write regardless of MTU
# (larger writes fail with "Invalid Attribute Value Length"); mBlock uses 64 as well.
WRITE_SIZE = 64
SAFE_WRITE_SIZE = 20  # always fits one ATT packet (minimum MTU 23)

warnings.filterwarnings("ignore", message="Using default MTU")


def _bleak_version() -> str:
    try:
        from importlib.metadata import version

        return version("bleak")
    except Exception:
        return "?"


class RobotError(RuntimeError):
    pass


@dataclass
class Found:
    address: str
    name: str
    rssi: int
    device: BLEDevice


async def scan(timeout: float = 5.0) -> list[Found]:
    seen = await BleakScanner.discover(timeout=timeout, return_adv=True)
    out = []
    for addr, (dev, adv) in seen.items():
        name = adv.local_name or dev.name or ""
        if name.startswith(NAME_PREFIX):
            out.append(Found(addr, name, adv.rssi, dev))
    return sorted(out, key=lambda f: -f.rssi)


async def find(target: str | None, timeout: float = 8.0) -> BLEDevice | str:
    """Resolve an address / name fragment / None (strongest robot) to a device."""
    if target and len(target) == 17 and target.count(":") == 5:
        dev = await BleakScanner.find_device_by_address(target, timeout=timeout)
        return dev or target  # BlueZ can often connect to a cached address anyway
    if target:  # name/address fragment: take the first match as soon as it shows up
        t = target.lower().replace(":", "")

        def match(dev: BLEDevice, adv) -> bool:
            name = (adv.local_name or dev.name or "").lower()
            return name.startswith(NAME_PREFIX.lower()) and (t in name or t in dev.address.lower().replace(":", ""))

        dev = await BleakScanner.find_device_by_filter(match, timeout=timeout)
        if dev is None:
            raise RobotError(f"No mBot2/CyberPi matching '{target}' found over Bluetooth.")
        return dev
    robots = await scan(min(timeout, 5.0))
    if not robots:
        raise RobotError(
            "No mBot2/CyberPi found over Bluetooth. Is it switched on (battery switch on the mBot2), "
            "and not connected to mBlock or another computer?"
        )
    return robots[0].device


class Robot:
    """One BLE session. Use as `async with Robot(target) as r:`."""

    def __init__(
        self,
        target: str | BLEDevice | None = None,
        on_text: Callable[[bytes], None] | None = None,
        log: Callable[[str], None] = lambda s: None,
    ):
        self.target = target
        self.log = log
        self.on_text = on_text or (lambda b: None)
        self.client: BleakClient | None = None
        self.reader = P.FrameReader(self._on_frame, self._on_text)
        self.frames: asyncio.Queue[P.Frame] = asyncio.Queue()
        self.ready = asyncio.Event()  # board announced itself after a boot
        self.disconnected = asyncio.Event()
        self.write_size = WRITE_SIZE
        self.closed = False
        self.write_response = os.environ.get("MBOT2_WRITE_RESPONSE", "0") != "0"
        self.debug = os.environ.get("MBOT2_DEBUG", "0") != "0"
        self.rebooting = asyncio.Event()  # board printed "PYB: ... reboot" or sent its ready frame
        self._idx = 0

    # ------------------------------------------------------------ plumbing
    async def __aenter__(self) -> "Robot":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def connect(self) -> None:
        dev = self.target if isinstance(self.target, BLEDevice) else await find(self.target)
        name = getattr(dev, "name", None) or getattr(dev, "address", dev)
        self.log(f"Connecting to {name}...")
        self.client = BleakClient(dev, timeout=20, disconnected_callback=lambda c: self.disconnected.set())
        await self.client.connect()
        self.write_size = SAFE_WRITE_SIZE
        if sys.platform.startswith("linux"):
            # BlueZ: run the MTU exchange explicitly; then 64-byte writes (the robot's maximum,
            # verified on hardware) are safe and ~3x faster.
            try:
                await self.client._backend._acquire_mtu()  # type: ignore[attr-defined]
                self.write_size = max(SAFE_WRITE_SIZE, min(WRITE_SIZE, self.client.mtu_size - 3))
            except Exception:
                pass
        # Elsewhere the reported MTU may not be what was negotiated yet, and an oversized write
        # gets split or dropped by the OS, so the robot never sees a whole frame. Stay at 20.
        if os.environ.get("MBOT2_WRITE_SIZE"):
            self.write_size = max(1, min(WRITE_SIZE, int(os.environ["MBOT2_WRITE_SIZE"])))
        await self.client.start_notify(NOTIFY, self._on_notify)
        self.log(f"Connected ({self.client.address}).")
        self.dlog(
            f"platform={sys.platform} python={sys.version.split()[0]} bleak={_bleak_version()} "
            f"mtu={self.client.mtu_size} "
            f"write_size={self.write_size} write_response={self.write_response}"
        )

    def dlog(self, msg: str) -> None:
        if self.debug:
            print(f"[debug {time.monotonic():.3f}] {msg}", file=sys.stderr, flush=True)

    async def close(self) -> None:
        self.closed = True  # BlueZ may keep delivering to a stale handler after a reconnect
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass

    @property
    def address(self) -> str:
        return self.client.address if self.client else ""

    def _on_notify(self, _char, data: bytearray) -> None:
        self.dlog(f"RX {bytes(data).hex(' ')}" + (" (stale session)" if self.closed else ""))
        if not self.closed:
            self.reader.feed(bytes(data))

    def _on_text(self, b: bytes) -> None:
        if b"PYB: " in b and b"reboot" in b:
            self.rebooting.set()
        self.on_text(b)

    def _on_frame(self, f: P.Frame) -> None:
        if f.is_ready():
            self.ready.set()
            self.rebooting.set()
        self.frames.put_nowait(f)

    async def write(self, data: bytes) -> None:
        if not self.client or not self.client.is_connected:
            raise RobotError("Bluetooth connection to the robot was lost.")
        for i in range(0, len(data), self.write_size):
            piece = data[i : i + self.write_size]
            self.dlog(f"TX {piece.hex(' ')}")
            await self.client.write_gatt_char(WRITE, piece, response=self.write_response)

    async def transact(
        self, data: bytes, match: Callable[[P.Frame], bool], label: str, timeout: float = 3.0, retries: int = 3
    ) -> P.Frame:
        for attempt in range(1, retries + 1):
            while not self.frames.empty():  # drop stale replies
                self.frames.get_nowait()
            await self.write(data)
            deadline = time.monotonic() + timeout
            while (left := deadline - time.monotonic()) > 0:
                try:
                    f = await asyncio.wait_for(self.frames.get(), left)
                except asyncio.TimeoutError:
                    break
                if match(f):
                    return f
                self.dlog(f"ignored frame while waiting for {label}: {f.body[:24].hex(' ')}")
            if self.disconnected.is_set():
                raise RobotError(f"Robot disconnected during {label}.")
            self.log(f"  {label}: no reply (attempt {attempt}/{retries})")
        raise RobotError(
            f"No reply from the robot for {label}. Make sure the mBot2's battery switch is on: with only "
            "USB power the CyberPi receives Bluetooth data but never answers. Also close mBlock/mLink."
        )

    # ------------------------------------------------------------ commands
    async def ping(self) -> None:
        """Puts the board in upload (offline) mode; the board echoes the frame."""
        await self.transact(P.UPLOAD_MODE, P.Frame.is_mode_echo, "upload-mode")

    async def eval(self, expr: str, timeout: float = 3.0):
        self._idx = (self._idx % 0xFFFF) + 1
        idx = self._idx
        f = await self.transact(
            P.script(expr, P.SCRIPT_EVAL, idx),
            lambda f: f.is_script_reply() and len(f.body) > 3 and f.body[2] | f.body[3] << 8 == idx,
            "eval",
            timeout,
            retries=1,
        )
        return f.script_result()

    async def exec(self, code: str) -> None:
        await self.transact(P.script(code), P.Frame.is_script_reply, "exec")

    async def _prepare(self, label: str) -> None:
        await self.ping()
        await self.transact(P.EXEC_IMPORT_CONFIG, P.Frame.is_script_reply, label)
        await self.transact(P.EXEC_REPL_OFF, P.Frame.is_script_reply, label)

    async def upload(
        self,
        source: bytes,
        name: str = "main",
        progress: Callable[[int, int], None] = lambda done, total: None,
    ) -> int:
        """Upload `source` as the board's program. Returns bytes sent on the wire."""
        data = P.pad_for_wire(source)
        parts = P.blocks(data)
        total = 1 + len(parts)
        for _ in range(2):  # mBlock sends the preamble twice
            await self._prepare("prepare")
        await self.transact(P.file_header(data, P.staging_path(name)), P.Frame.is_file_ack, "file header")
        progress(1, total)
        for n, (offset, chunk) in enumerate(parts, start=2):
            await self.transact(P.file_block(offset, chunk), P.Frame.is_file_ack, f"block @{offset}")
            progress(n, total)
        await self._prepare("finish")
        return len(data)

    async def enable_print(self) -> None:
        """Mirror the running program's print() output to Bluetooth (until the next restart)."""
        await self.exec("import global_objects\nglobal_objects.makeblock.set_ble_print_flag(1)")

    async def _wait_any(self, events: list[asyncio.Event], timeout: float) -> bool:
        tasks = [asyncio.ensure_future(e.wait()) for e in events]
        try:
            done, _ = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            return bool(done)
        finally:
            for t in tasks:
                t.cancel()

    async def wait_for_reboot(self, timeout: float) -> bool:
        return await self._wait_any([self.rebooting, self.disconnected], timeout)

    async def reboot(self, wait: float = 6.0) -> bool:
        """Restart the board (machine.reset). True if a restart was seen."""
        self.rebooting.clear()
        try:
            await self.write(P.EXEC_RESET)
        except Exception:
            pass
        return await self.wait_for_reboot(wait)


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)
