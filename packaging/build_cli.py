"""Build a standalone `mbot2` executable (no Python needed to run it) with PyInstaller.

    uv run --with pyinstaller python packaging/build_cli.py

Writes dist/mbot2-<platform>-<arch>[.exe], e.g. dist/mbot2-windows-x64.exe. The release
workflow (.github/workflows/release.yml) runs this on each OS and attaches the results to a
GitHub release; the VS Code extension bundles them under vscode/bin/.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OS_NAMES = {"linux": "linux", "win32": "windows", "darwin": "macos"}
ARCH_NAMES = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def target_name() -> str:
    os_name = OS_NAMES.get(sys.platform)
    arch = ARCH_NAMES.get(platform.machine().lower())
    if not os_name or not arch:
        sys.exit(f"unsupported platform: {sys.platform} {platform.machine()}")
    return f"mbot2-{os_name}-{arch}"


def main() -> None:
    name = target_name()
    dist = ROOT / "dist"
    with tempfile.TemporaryDirectory() as tmp:
        entry = Path(tmp) / "mbot2_entry.py"
        entry.write_text("import sys\nfrom mbot2 import main\nsys.exit(main())\n")
        subprocess.run(
            [
                sys.executable, "-m", "PyInstaller",
                "--onefile", "--noconfirm", "--console",
                "--name", name,
                "--paths", str(ROOT / "src"),
                "--collect-submodules", "bleak",  # backends are imported lazily per OS
                "--copy-metadata", "bleak",  # shown by -v
                "--copy-metadata", "mbot2",  # shown by --version
                "--distpath", str(dist),
                "--workpath", str(Path(tmp) / "build"),
                "--specpath", tmp,
                str(entry),
            ],
            check=True,
        )
    exe = dist / (name + (".exe" if sys.platform == "win32" else ""))
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, check=True)
    print(f"built {exe} ({exe.stat().st_size / 1e6:.1f} MB): {out.stdout.strip()}")


if __name__ == "__main__":
    main()
