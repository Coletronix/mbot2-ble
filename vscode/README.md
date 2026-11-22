# mBot2 Upload for VS Code

Adds an **Upload to mBot2** button (cloud icon, top right of the editor) to Python files.
Click it, pick your robot, and the file is uploaded over Bluetooth and started. The
program's `print()` output then appears in the **mBot2** terminal.

Everything it needs is built in: you don't have to install Python or the `mbot2`
command-line tool.

## Using it

1. Open your program (it needs an `@event.start` handler, like `examples/hello.py`).
2. Click the cloud button at the top right (or press `Ctrl+Alt+U`, or right-click the file
   in the Explorer). Unsaved changes are saved first.
3. A list of robots in range appears after a few seconds. Check the name printed on the
   side of **your** robot and click it. If the robot you used last is in range it's
   at the top and already selected, so **Enter** picks it.

**One click instead of two:** click the pin next to a robot in the list. Uploads from this
workspace then go straight to that robot. The status bar shows the pinned robot; click it
to go back to choosing each time. Or set `mbot2.device` in Settings to an address or the
last few characters of the robot's name.

Like the CLI, it never picks a robot by itself just because it's the only one in range.
In a classroom, that robot may be someone else's.

Other commands (Ctrl+Shift+P, type "mBot2"): **Show Robot Output** and **Stop Showing
Robot Output (Disconnect)**. The robot accepts only one Bluetooth connection, so the
output view is stopped before each scan or upload. Close mBlock too.

## Settings

| setting | default | |
|---|---|---|
| `mbot2.device` | *(empty)* | always use this robot (address or name fragment) |
| `mbot2.monitorAfterUpload` | `true` | show `print()` output after uploading |
| `mbot2.scanSeconds` | `4` | how long to scan before listing robots |
| `mbot2.command` | *(empty)* | empty: use the built-in uploader. Or `mbot2` / a full path to use a separately installed CLI (`~/.local/bin` is searched even when it's not on VS Code's PATH) |
| `mbot2.verbose` | `false` | log every Bluetooth packet (for bug reports) |

## Install

1. Download **[mbot2-upload.vsix](https://github.com/Coletronix/mbot2-ble/releases/latest/download/mbot2-upload.vsix)**
   (one file for Windows, Linux and Apple Silicon Macs).
2. In VS Code: Extensions view (`Ctrl+Shift+X`) → `···` menu at the top → **Install from VSIX…**
   → pick the file. Or from a terminal: `code --install-extension mbot2-upload.vsix`
   (`codium` for VSCodium).

To update, install a newer `.vsix` the same way.

On other computers (Intel Macs, 32-bit Linux) the extension has no built-in uploader; install
the command-line tool [from source](../README.md#from-source) and it's used automatically.

## Building it

`npm test` runs the helper tests (no VS Code needed). `npm run package` makes a `.vsix`
that uses an `mbot2` installed on your PATH. The release workflow additionally puts the
standalone programs from `packaging/build_cli.py` in `bin/<platform>-<arch>/`, which the
extension prefers.
