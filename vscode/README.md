# mBot2 Upload for VS Code

Adds an **Upload to mBot2** button (cloud icon, top right of the editor) to Python files.
Click it, pick your robot, and the file is uploaded over Bluetooth and started. The
program's `print()` output then appears in the **mBot2** terminal.

It drives the `mbot2` command-line tool from this repository, so install that first
(see the [main README](../README.md)): `uv tool install .` in the repository root.

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
| `mbot2.command` | `mbot2` | path to the CLI; `~/.local/bin` is searched even when it's not on VS Code's PATH |
| `mbot2.verbose` | `false` | log every Bluetooth packet (for bug reports) |

## Install

Build the package and install it (needs Node.js):

```sh
cd vscode
npm run package                                     # makes mbot2-upload-0.1.0.vsix
code --install-extension mbot2-upload-0.1.0.vsix    # or: codium --install-extension ...
```

Or in VS Code: Extensions view → `…` menu → **Install from VSIX…**.

Tests: `npm test` (helpers only; no VS Code needed).
