# mbot2 — upload MicroPython to an mBot2 / CyberPi over Bluetooth

A small CLI that uploads a `.py` program to a Makeblock mBot2 (CyberPi) over
Bluetooth LE, restarts it, and streams the program's `print()` output back.
No mBlock, no mLink, no USB cable.

```console
$ mbot2 upload examples/hello.py --monitor
Connecting to Makeblock_LE5443B2XXXXXX…
Uploading hello.py (364 bytes) as 'main'…
Uploaded 404 bytes in 4.1s.
Robot restarted; the new program is running.
Monitoring robot output — Ctrl-C to stop.
heartbeat 0
heartbeat 1
```

## Requirements

- **[uv](https://docs.astral.sh/uv/getting-started/installation/)**: installs the tool
  and fetches a suitable Python (3.11+) by itself.
  `curl -LsSf https://astral.sh/uv/install.sh | sh` (or your package manager,
  e.g. `pacman -S uv`, `brew install uv`).
- **git**, to clone this repository.
- **A Bluetooth LE adapter.** On Linux, **BlueZ** with the `bluetooth` service running
  (`sudo systemctl enable --now bluetooth`; `bluetoothctl show` should say
  `Powered: yes`). No pairing is needed and no special permissions beyond
  normal BlueZ access. Tested on Linux. [bleak](https://github.com/hbldh/bleak) also
  supports macOS and Windows, but this tool hasn't been tested there.
- An mBot2 / CyberPi with the mBot2's battery switch **on**.

## Install

```sh
git clone https://github.com/Coletronix/mbot2-ble.git
cd mbot2-ble
uv tool install .                 # puts `mbot2` on your PATH (~/.local/bin)
```

For development, use `uv tool install --editable .` or run in place with
`uv run mbot2 …`. Tests run with `uv run pytest`.

## Commands

| command | what it does |
|---|---|
| `mbot2 scan` | list Makeblock robots nearby (`*` = remembered one) |
| `mbot2 upload FILE [-m]` | upload FILE as the robot's program, restart, optionally monitor output |
| `mbot2 monitor` | stream the running program's `print()` output (reconnects across restarts) |
| `mbot2 eval EXPR` | evaluate an expression on the robot, print the result |
| `mbot2 exec CODE` | run a snippet on the robot |
| `mbot2 reset` | restart the robot |
| `mbot2 forget` | forget the remembered robot |

Robot selection: `-d ADDRESS` or `-d NAMEFRAGMENT` (e.g. `-d 427a`), else
`$MBOT2_DEVICE`, else the last robot used (stored in
`~/.config/mbot2/config.json`), else the strongest one nearby.

## Things to know

- **Turn the mBot2's battery switch on.** With only USB power, the CyberPi
  receives Bluetooth/serial data but never answers.
- Programs must register an entry point such as `@event.start`. The tool
  refuses files without one, and files with syntax errors (`--force` overrides).
  Programs with only top-level code have been reported to hang the CyberPi at boot.
- The upload goes to the firmware's staging slot (`/flash/_xx_main.py`). The
  firmware swaps it in when it restarts, so an interrupted upload leaves the
  old program in place.
- `print()` output is only sent over Bluetooth after
  `global_objects.makeblock.set_ble_print_flag(1)`. `monitor`/`exec` turn this
  on for each connection; it resets when the robot restarts.
- Don't `eval` filesystem calls (`os.listdir`…) or import internal modules
  such as `internal_lib`. Both crash/restart the board from the protocol handler.
- Only one BLE client at a time: close mBlock first.

## Protocol notes

The Makeblock "F3/F4" framing (see `src/mbot2/protocol.py`):

```
F3  (F3+len_lo+len_hi)&FF  len_lo len_hi  body…  sum(body)&FF  F4
```

| step | body |
|---|---|
| upload mode | `0D 00 00` (echoed) |
| prepare ×2 | exec `import config`, exec `config.write_config("repl_enable", False)` — `28 04 <idx16> <len16> <src>` |
| file header | `01 00 5E 01 <len16> 00 <size32> <xor32> /flash/_xx_main.py` |
| blocks | `01 00 5E 02 <len16> <offset32> <data>`: 80-byte blocks, then exactly the last 4 bytes; source padded with `\n` to `size % 80 == 4` |
| finish | upload mode + prepare again; the board prints `PYB: fast reboot` and restarts |

Eval is the same script frame with mode `0x01`; the reply is `{"ret": …}`.
BLE: service `ffe1`, write `ffe3` (**max 64 bytes per write**), notify `ffe2`.

Credits: framing from Makeblock's `makeblock` PyPI package (`HalocodePackData`);
upload sequence as decoded by
[dachrisch/mbot2-course-setup](https://github.com/dachrisch/mbot2-course-setup) and
[weare2plus3/cyberpi-uploader](https://github.com/weare2plus3/cyberpi-uploader) (USB);
BLE specifics (64-byte writes, print forwarding) found on this robot.
