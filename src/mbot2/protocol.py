"""Makeblock CyberPi (mBot2) "F3/F4" wire protocol.

Pure functions only (no I/O) so they can be unit-tested.

Frame:  F3  hdr  len_lo  len_hi  body...  ck  F4
        hdr = (0xF3 + len_lo + len_hi) & 0xFF
        ck  = sum(body) & 0xFF

Bodies used here:
  ping / upload mode   0D 00 00                         (board echoes it)
  script               28 <mode> <idx16> <len16> <utf8 python>
                         mode 0x04 = exec (reply {"ret":None})
                         mode 0x01 = eval, reply {"ret":<value>}
  file header          01 00 5E 01 <len16> 00 <size32> <xor32> <path>
  file block           01 00 5E 02 <len16> <offset32> <data>

The upload sequence and block shape match what mBlock 5 sends (and what
has been confirmed on real hardware): data [0, size-4) in 80-byte blocks,
then exactly the last 4 bytes as a final block. The source is padded with
trailing newlines so that size % 80 == 4.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Callable, Iterator

HEAD = 0xF3
TAIL = 0xF4

TYPE_SCRIPT = 0x28
TYPE_MODE = 0x0D
TYPE_READY = 0x08  # board says hello after boot (F3 F5 ... 08 ...)

SCRIPT_EVAL = 0x01
SCRIPT_EXEC = 0x04

STAGING_DIR = "/flash/_xx_"  # firmware moves /flash/_xx_<name>.py into place on boot
BLOCK = 80
MAX_BODY = 4096


def frame(body: bytes) -> bytes:
    n = len(body)
    if n > 0xFFFF:
        raise ValueError("frame body too large")
    lo, hi = n & 0xFF, n >> 8
    return bytes([HEAD, (HEAD + lo + hi) & 0xFF, lo, hi]) + body + bytes([sum(body) & 0xFF, TAIL])


# --------------------------------------------------------------- commands

UPLOAD_MODE = frame(bytes([TYPE_MODE, 0x00, 0x00]))
DEBUG_MODE = frame(bytes([TYPE_MODE, 0x00, 0x01]))


def script(code: str, mode: int = SCRIPT_EXEC, idx: int = 0) -> bytes:
    src = code.encode("utf-8")
    return frame(struct.pack("<BBHH", TYPE_SCRIPT, mode, idx & 0xFFFF, len(src)) + src)


EXEC_IMPORT_CONFIG = script("try:\n    import config\nexcept:\n    pass")
EXEC_REPL_OFF = script('try:\n    config.write_config("repl_enable", False)\nexcept:\n    pass')
EXEC_RESET = script("import machine\nmachine.reset()")


def xor32(data: bytes) -> int:
    """XOR of little-endian 32-bit words, zero padded (mBlock's file checksum)."""
    data = data + b"\0" * (-len(data) % 4)
    x = 0
    for (w,) in struct.iter_unpack("<I", data):
        x ^= w
    return x


def _ftp(cmd: int, payload: bytes) -> bytes:
    return frame(bytes([0x01, 0x00, 0x5E, cmd]) + struct.pack("<H", len(payload)) + payload)


def file_header(data: bytes, path: str) -> bytes:
    return _ftp(0x01, b"\x00" + struct.pack("<II", len(data), xor32(data)) + path.encode("utf-8"))


def file_block(offset: int, chunk: bytes) -> bytes:
    return _ftp(0x02, struct.pack("<I", offset) + chunk)


def pad_for_wire(data: bytes) -> bytes:
    """Pad with newlines so len % 80 == 4 (the block shape mBlock produces)."""
    return data + b"\n" * ((4 - len(data)) % BLOCK)


def blocks(data: bytes) -> list[tuple[int, bytes]]:
    """[0, size-4) in BLOCK-sized pieces, then the last 4 bytes."""
    if len(data) <= 4:
        return [(0, data)]
    end = len(data) - 4
    out = [(o, data[o : min(o + BLOCK, end)]) for o in range(0, end, BLOCK)]
    out.append((end, data[end:]))
    return out


def staging_path(name: str = "main") -> str:
    return f"{STAGING_DIR}{name}.py"


# --------------------------------------------------------------- replies

@dataclass(frozen=True)
class Frame:
    body: bytes

    @property
    def type(self) -> int:
        return self.body[0] if self.body else -1

    def is_mode_echo(self) -> bool:
        return len(self.body) == 3 and self.body[0] == TYPE_MODE

    def is_script_reply(self) -> bool:
        return self.type == TYPE_SCRIPT

    def is_file_ack(self) -> bool:
        return len(self.body) >= 3 and self.body[:3] == b"\x01\x00\x5e"

    def is_ready(self) -> bool:
        return self.type == TYPE_READY

    def script_result(self):
        """Decode {"ret": ...} of a script reply (Python-literal-ish JSON)."""
        if len(self.body) < 6:
            return None
        n = struct.unpack_from("<H", self.body, 4)[0]
        text = self.body[6 : 6 + n].decode("utf-8", "replace")
        try:
            return json.loads(text)["ret"]
        except Exception:
            js = text.replace("None", "null").replace("True", "true").replace("False", "false").replace("'", '"')
            try:
                return json.loads(js)["ret"]
            except Exception:
                return text


class FrameReader:
    """Splits a byte stream into F3..F4 frames and plain text (program stdout)."""

    def __init__(self, on_frame: Callable[[Frame], None], on_text: Callable[[bytes], None]):
        self.buf = bytearray()
        self.on_frame = on_frame
        self.on_text = on_text

    def feed(self, data: bytes) -> None:
        self.buf.extend(data)
        for item in self._drain():
            (self.on_frame if isinstance(item, Frame) else self.on_text)(item)

    def _drain(self) -> Iterator[Frame | bytes]:
        b = self.buf
        while b:
            start = b.find(HEAD)
            if start < 0:
                yield bytes(b)
                b.clear()
                return
            if start:
                yield bytes(b[:start])
                del b[:start]
            if len(b) < 4:
                return
            n = b[2] | (b[3] << 8)
            if (HEAD + b[2] + b[3]) & 0xFF != b[1] or n > MAX_BODY:
                yield bytes(b[:1])
                del b[:1]
                continue
            if len(b) < n + 6:
                return
            body = bytes(b[4 : 4 + n])
            if b[4 + n] != sum(body) & 0xFF or b[5 + n] != TAIL:
                yield bytes(b[:1])
                del b[:1]
                continue
            del b[: n + 6]
            yield Frame(body)
