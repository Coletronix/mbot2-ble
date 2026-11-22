import sys
from pathlib import Path

import pytest

from mbot2 import cli

GOOD = b"import event\n\n\n@event.start\ndef on_start():\n    print('hi')\n"


def test_read_source_strips_bom_and_keeps_crlf(tmp_path: Path):
    f = tmp_path / "prog.py"
    f.write_bytes(b"\xef\xbb\xbf" + GOOD.replace(b"\n", b"\r\n"))
    src = cli.read_source(f)
    assert not src.startswith(b"\xef\xbb\xbf")
    assert cli.check_source(src, f) == []


def test_check_source_flags_problems(tmp_path: Path):
    f = tmp_path / "p.py"
    assert cli.check_source(GOOD, f) == []
    assert any("event" in p for p in cli.check_source(b"print(1)\n", f))
    assert any("syntax" in p for p in cli.check_source(b"def f(:\n", f))
    assert cli.check_source(b"\xff\xfe", f) == ["file is not valid UTF-8"]


def test_config_dir_windows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert cli._config_dir() == tmp_path / "mbot2"


def test_config_dir_posix(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cli._config_dir() == tmp_path / "mbot2"


def test_config_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "CONFIG", tmp_path / "sub" / "config.json")
    cli.save_config(device="AA:BB:CC:DD:EE:FF")
    assert cli.load_config() == {"device": "AA:BB:CC:DD:EE:FF"}


def test_upload_refuses_bad_file_without_bluetooth(tmp_path: Path, capsys):
    f = tmp_path / "bare.py"
    f.write_text("print(1)\n")
    assert cli.main(["upload", str(f)]) == 2
    assert "Refusing" in capsys.readouterr().err


def test_help_works():
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0


def test_scan_json(monkeypatch, tmp_path: Path, capsys):
    import json

    from mbot2.device import Found

    async def fake_scan(timeout):
        return [Found("AA:BB:CC:DD:EE:01", "Makeblock_LE01", -50, None),
                Found("AA:BB:CC:DD:EE:02", "Makeblock_LE02", -70, None)]

    monkeypatch.setattr(cli, "scan", fake_scan)
    monkeypatch.setattr(cli, "CONFIG", tmp_path / "config.json")
    cli.save_config(device="AA:BB:CC:DD:EE:02")
    assert cli.main(["scan", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in out] == ["Makeblock_LE01", "Makeblock_LE02"]
    assert [r["last_used"] for r in out] == [False, True]
    assert out[0]["rssi"] == -50


def test_bluetooth_message_explains_common_failures():
    from bleak.exc import BleakBluetoothNotAvailableError, BleakBluetoothNotAvailableReason as R, BleakError

    from mbot2.cli import bluetooth_message

    assert "turned off" in bluetooth_message(BleakBluetoothNotAvailableError("off", R.POWERED_OFF))
    assert "No usable Bluetooth" in bluetooth_message(BleakBluetoothNotAvailableError("x", R.NO_BLUETOOTH))
    assert "allowed" in bluetooth_message(BleakBluetoothNotAvailableError("x", R.DENIED_BY_USER))
    msg = "[org.freedesktop.DBus.Error.ServiceUnknown] The name org.bluez was not provided by any .service files"
    assert "systemctl enable --now bluetooth" in bluetooth_message(BleakError(msg))
    assert bluetooth_message(BleakError("weird")) == "Bluetooth: weird"
