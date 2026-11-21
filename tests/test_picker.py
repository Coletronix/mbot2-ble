import asyncio
from types import SimpleNamespace

import pytest

from mbot2 import cli
from mbot2.device import Found, RobotError
from mbot2.picker import format_list, parse_choice, pick_robot


def robot(name, addr, rssi=-50):
    return Found(addr, name, rssi, device=SimpleNamespace(address=addr, name=name))


A = robot("Makeblock_LE5443B213427A", "54:43:B2:13:42:7A")
B = robot("Makeblock_LE5443B2C3F100", "54:43:B2:C3:F1:00", -70)


def test_parse_number_and_name_fragment():
    assert parse_choice("1", [A, B]).index == 0
    assert parse_choice(" 2 ", [A, B]).index == 1
    assert parse_choice("427a", [A, B]).index == 0  # last characters printed on the robot
    assert parse_choice("LE5443B2C3F100", [A, B]).index == 1
    assert parse_choice("Makeblock_LE5443B213427A", [A, B]).index == 0


def test_parse_rejects_ambiguous_and_unknown():
    assert parse_choice("5443B2", [A, B]).action == "invalid"  # matches both
    assert parse_choice("ZZZZ", [A, B]).action == "invalid"
    assert parse_choice("3", [A, B]).action == "invalid"
    assert parse_choice("0", [A]).action == "invalid"
    assert parse_choice("", [A]).action == "invalid"  # Enter never picks a robot that wasn't used before
    assert parse_choice("", [A], last_used=B.address).action == "invalid"  # last-used robot not in range


def test_enter_reuses_last_used_robot():
    assert parse_choice("", [A, B], last_used=B.address).index == 1
    assert parse_choice("  ", [B], last_used=B.address).index == 0


def test_parse_rescan_quit():
    assert parse_choice("r", [A]).action == "rescan"
    assert parse_choice("", []).action == "rescan"
    assert parse_choice("q", [A]).action == "quit"


def test_list_marks_last_used():
    out = format_list([A, B], last_used=B.address)
    assert "1) Makeblock_LE5443B213427A" in out and "last used" in out.splitlines()[1]


def run_picker(answers, scans, last_used=None):
    answers, scans = list(answers), list(scans)

    async def ask(_):
        if not answers:
            raise EOFError
        return answers.pop(0)

    async def find():
        return scans.pop(0)

    return asyncio.run(pick_robot(last_used, ask=ask, find=find))


def test_single_robot_still_requires_a_choice():
    # Enter alone doesn't pick the only robot if it wasn't used before; an explicit "1" does.
    assert run_picker(["", "1"], [[A]]) is A
    assert run_picker([""], [[A, B]], last_used=A.address) is A


def test_rescan_then_pick_by_name():
    assert run_picker(["", "c3f100"], [[], [A, B]]) is B


def test_quit_and_eof():
    with pytest.raises(RobotError):
        run_picker(["q"], [[A]])
    with pytest.raises(RobotError):
        run_picker([], [[A]])


def test_no_terminal_means_no_guessing(monkeypatch, tmp_path):
    monkeypatch.delenv("MBOT2_DEVICE", raising=False)
    monkeypatch.delenv("MBOT2_AUTO", raising=False)
    monkeypatch.setattr(cli, "CONFIG", tmp_path / "config.json")
    cli.save_config(device=A.address)  # a remembered robot must not be used silently either
    monkeypatch.setattr(cli, "can_prompt", lambda: False)
    args = SimpleNamespace(device=None, auto=False)
    with pytest.raises(RobotError, match="-d"):
        asyncio.run(cli.target_of(args))


def test_explicit_device_skips_picker(monkeypatch):
    monkeypatch.delenv("MBOT2_DEVICE", raising=False)
    assert asyncio.run(cli.target_of(SimpleNamespace(device="427a", auto=False))) == "427a"
    monkeypatch.setenv("MBOT2_DEVICE", "54:43:B2:13:42:7A")
    assert asyncio.run(cli.target_of(SimpleNamespace(device=None, auto=False))) == "54:43:B2:13:42:7A"


def test_auto_uses_single_robot_only(monkeypatch):
    monkeypatch.delenv("MBOT2_DEVICE", raising=False)
    monkeypatch.setattr(cli, "can_prompt", lambda: False)

    async def one(_t):
        return [A]

    async def two(_t):
        return [A, B]

    monkeypatch.setattr(cli, "scan", one)
    args = SimpleNamespace(device=None, auto=True)
    assert asyncio.run(cli.target_of(args)) is A.device
    assert args._target == A.address
    monkeypatch.setattr(cli, "scan", two)
    with pytest.raises(RobotError):  # two robots: must choose, and can't prompt here
        asyncio.run(cli.target_of(SimpleNamespace(device=None, auto=True)))
