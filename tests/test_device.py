import asyncio

from mbot2 import protocol as P
from mbot2.device import Robot


class LossyClient:
    """Stands in for a Windows BLE stack that silently drops unacknowledged writes."""

    is_connected = True

    def __init__(self, robot: Robot):
        self.robot = robot
        self.buf = b""
        self.writes = []

    async def write_gatt_char(self, _char, data, response):
        self.writes.append(response)
        if not response:
            return  # dropped
        self.buf += data
        if self.buf.endswith(bytes([P.TAIL])):
            self.robot._on_notify(None, bytearray(self.buf))  # robot echoes the ping
            self.buf = b""


def test_falls_back_to_acknowledged_writes(monkeypatch):
    monkeypatch.delenv("MBOT2_WRITE_RESPONSE", raising=False)

    async def go():
        r = Robot(log=lambda s: None)
        r.write_response = False  # what Linux defaults to
        r.client = LossyClient(r)
        await r.transact(P.UPLOAD_MODE, P.Frame.is_mode_echo, "upload-mode", timeout=0.2, retries=1)
        return r

    r = asyncio.run(go())
    assert r.write_response is True
    assert r.client.writes[0] is False and r.client.writes[-1] is True


def test_write_mode_defaults(monkeypatch):
    import sys

    monkeypatch.delenv("MBOT2_WRITE_RESPONSE", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert Robot().write_response is True
    monkeypatch.setattr(sys, "platform", "linux")
    assert Robot().write_response is False
    monkeypatch.setenv("MBOT2_WRITE_RESPONSE", "0")
    monkeypatch.setattr(sys, "platform", "win32")
    assert Robot().write_response is False
