# mbot2 — upload MicroPython to an mBot2 / CyberPi over Bluetooth

Uploads a `.py` program to a Makeblock mBot2 (CyberPi) over Bluetooth LE, restarts it,
and streams the program's `print()` output back. Use it from a one-click button in
VS Code, or as the `mbot2` command-line tool. No mBlock, no mLink, no USB cable.

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

## Install

You don't need Python, git, or anything else. Pick **one** of these.

### Option 1: VS Code extension (easiest)

Adds an upload button to VS Code (or VSCodium). Everything it needs is inside one file.

1. Download **[mbot2-upload.vsix](https://github.com/Coletronix/mbot2-ble/releases/latest/download/mbot2-upload.vsix)**.
2. In VS Code, open the **Extensions** view (`Ctrl+Shift+X`, or the four-squares icon on the left).
3. Click the **`···`** menu at the top of that view → **Install from VSIX…** → pick the file you downloaded.
4. Open a robot program (try [`examples/hello.py`](examples/hello.py)) and click the
   **cloud button** at the top right of the editor. Pick your robot from the list, and that's it.

More about the extension: [vscode/README.md](vscode/README.md).

### Option 2: command-line tool

Copy this line into a terminal and press Enter:

| | |
|---|---|
| **Windows** (open *PowerShell* from the Start menu) | `irm https://github.com/Coletronix/mbot2-ble/releases/latest/download/install.ps1 \| iex` |
| **Linux / macOS** | `curl -LsSf https://github.com/Coletronix/mbot2-ble/releases/latest/download/install.sh \| sh` |

Then open a new terminal and run `mbot2 scan` to check it works. Run the same line again
later to update.

<details>
<summary>Or download the program yourself</summary>

| your computer | file |
|---|---|
| Windows (64-bit) | [mbot2-windows-x64.exe](https://github.com/Coletronix/mbot2-ble/releases/latest/download/mbot2-windows-x64.exe) |
| Linux (64-bit PC) | [mbot2-linux-x64](https://github.com/Coletronix/mbot2-ble/releases/latest/download/mbot2-linux-x64) |
| Linux (ARM 64-bit, e.g. Raspberry Pi OS 64-bit) | [mbot2-linux-arm64](https://github.com/Coletronix/mbot2-ble/releases/latest/download/mbot2-linux-arm64) |
| macOS (Apple Silicon: M1 and later) | [mbot2-macos-arm64](https://github.com/Coletronix/mbot2-ble/releases/latest/download/mbot2-macos-arm64) |

Rename it to `mbot2` (`mbot2.exe` on Windows) and put it in a folder on your PATH. On
Linux/macOS, make it runnable with `chmod +x mbot2`. On Windows, a browser download may show
"Windows protected your PC": click **More info → Run anyway** (the install line above avoids this).
All files are on the [releases page](https://github.com/Coletronix/mbot2-ble/releases/latest),
with SHA-256 checksums.
</details>

### Before your first upload

- **Turn Bluetooth on.** Most laptops have it; desktops may need a USB dongle. Don't pair
  the robot in your computer's Bluetooth settings: the tool connects without pairing.
  - **Windows 10 (1709+) / 11:** Settings → Bluetooth & devices → Bluetooth **On**.
  - **Linux:** BlueZ with the `bluetooth` service running: `sudo systemctl enable --now bluetooth`.
    `bluetoothctl show` should say `Powered: yes`.
  - **macOS:** the first time, allow Bluetooth access when asked (or under System Settings →
    Privacy & Security → Bluetooth, for your terminal app or VS Code).
- **Turn the mBot2's battery switch on.** USB power alone isn't enough.
- **Close mBlock.** The robot only accepts one Bluetooth connection at a time.

Tested with a real robot on Linux. Windows and macOS use [bleak](https://github.com/hbldh/bleak)'s
native backends; every release is built and started on all three.

### From source

For working on the tool itself. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/),
which also fetches a suitable Python (3.11+), and git.

```sh
git clone https://github.com/Coletronix/mbot2-ble.git
cd mbot2-ble
uv tool install .                 # puts `mbot2` on your PATH (~/.local/bin)
```

If your shell then says `mbot2` isn't found, run `uv tool update-shell` and open a
new terminal. To update later: `git pull` then `uv tool install --reinstall .`
For development, use `uv tool install --editable .` or run in place with
`uv run mbot2 ...`. Tests run with `uv run pytest`.

To build the standalone program yourself: `uv run --with pyinstaller python packaging/build_cli.py`
(writes `dist/mbot2-<os>-<arch>`).

## Commands

| command | what it does |
|---|---|
| `mbot2 scan [--json]` | list Makeblock robots nearby |
| `mbot2 upload FILE [-m]` | upload FILE as the robot's program, restart, optionally monitor output |
| `mbot2 monitor` | stream the running program's `print()` output (reconnects across restarts) |
| `mbot2 eval EXPR` | evaluate an expression on the robot, print the result |
| `mbot2 exec CODE` | run a snippet on the robot |
| `mbot2 reset` | restart the robot |
| `mbot2 forget` | clear the "last used" mark |

### Choosing the robot

By default every command asks which robot to use, **even when only one is in range**. In
a classroom, the only robot in range may belong to someone else, and uploading to it
silently would overwrite their program.

```console
$ mbot2 upload my_program.py
Scanning for robots...
Found 2 robots:
  1) Makeblock_LE5443B213427A   signal ###.  54:43:B2:13:42:7A   <- last used on this computer
  2) Makeblock_LE5443B2C3F100   signal ##..  54:43:B2:C3:F1:00
Check the name printed on the side of YOUR robot. Type its number in the list, or the last few characters of its name. 'r' rescans, 'q' quits.
Your robot: 427a
```

Each robot's name is printed on its side; type the list number or the last few characters
of that name. Pressing Enter reuses the robot this computer used last, but only if
that robot is in the list right now; otherwise Enter does nothing.

To skip the list:

- `-d ADDRESS` or `-d NAMEFRAGMENT` (e.g. `-d 427a`), or set `$MBOT2_DEVICE`.
- `--auto` / `-a` (or `$MBOT2_AUTO=1`): if exactly one robot is in range, use it without
  asking. With several robots in range you still get the list. Handy at home; risky in
  a classroom.

When there's no terminal to ask in (scripts, editor tasks that don't take input), you must
pass `-d`, set `$MBOT2_DEVICE`, or use `--auto`. The tool never guesses. The last robot
used (stored in `~/.config/mbot2/config.json`, or `%APPDATA%\mbot2\config.json` on
Windows) is marked in the list and is what Enter picks, but it's never used without someone pressing
a key. On a shared computer it may be another student's, so check the name.

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
- Bluetooth writes: on Linux, 64-byte writes that the robot doesn't acknowledge (fastest).
  Elsewhere, 20-byte acknowledged writes, because Windows was seen silently dropping
  unacknowledged ones and the robot rejects writes over 64 bytes. If a command goes
  unanswered with unacknowledged writes, the tool switches to acknowledged ones by itself.
  Override with `MBOT2_WRITE_RESPONSE=0|1` and `MBOT2_WRITE_SIZE=N`.
- Problems? Run with `-v` (e.g. `mbot2 -v upload prog.py`) to log the connection settings
  and every packet, and include that output in a bug report.
- Only one BLE client at a time: close mBlock first. On Windows, if a robot was
  paired in Bluetooth settings and won't connect, remove it there and try again.

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

## Releasing

1. Set the same version in `pyproject.toml` and `vscode/package.json` (e.g. `0.2.0`), run
   `uv lock`, and commit.
2. `git tag v0.2.0 && git push origin v0.2.0`

The [Release workflow](.github/workflows/release.yml) builds the standalone programs on
Linux (x64, arm64), Windows and macOS, bundles them into the VS Code extension, publishes a
GitHub release, and then installs from that release to check the download links. File names
carry no version, so the `releases/latest/download/...` links in this README always get the
newest release. To try a build without publishing, run the workflow from the Actions tab
and download the files from the run.
