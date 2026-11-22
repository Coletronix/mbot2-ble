// Helpers that don't need the VS Code API (unit-tested with `node --test`).
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

/** Find an executable the way a shell would, plus uv's tool folder (~/.local/bin), which
 * often isn't on the PATH VS Code was started with (desktop launchers, Windows). */
function findExecutable(command, env = process.env, platform = process.platform) {
  const isWin = platform === "win32";
  const exts = isWin
    ? ["", ...(env.PATHEXT || ".EXE;.CMD;.BAT;.COM").split(";").filter(Boolean)]
    : [""];
  const tryFile = (p) => {
    for (const ext of exts) {
      const f = p + ext;
      try {
        if (fs.statSync(f).isFile()) {
          if (!isWin) fs.accessSync(f, fs.constants.X_OK);
          return f;
        }
      } catch {
        /* keep looking */
      }
    }
    return null;
  };
  if (command.includes("/") || (isWin && command.includes("\\"))) {
    return tryFile(command.replace(/^~(?=$|[\\/])/, os.homedir()));
  }
  const pathVar = env.PATH || env.Path || "";
  const dirs = pathVar.split(isWin ? ";" : ":").filter(Boolean);
  dirs.push(path.join(os.homedir(), ".local", "bin"));
  for (const d of dirs) {
    const hit = tryFile(path.join(d, command));
    if (hit) return hit;
  }
  return null;
}

/** Folders under bin/ to try for this computer, best first. The release build puts a
 * standalone mbot2 there for each supported platform (see packaging/build_cli.py). Windows on
 * ARM runs the x64 build under emulation. */
function bundledCandidates(extensionPath, platform = process.platform, arch = process.arch) {
  const exe = platform === "win32" ? "mbot2.exe" : "mbot2";
  const dirs = [`${platform}-${arch}`];
  if (platform === "win32" && arch === "arm64") dirs.push("win32-x64");
  return dirs.map((d) => path.join(extensionPath, "bin", d, exe));
}

/** Which mbot2 to run: the `mbot2.command` setting if set, else the copy bundled with the
 * extension, else `mbot2` from the PATH (a source install). Returns a path or null. */
function resolveMbot2(setting, extensionPath, env = process.env, platform = process.platform, arch = process.arch) {
  const command = (setting || "").trim();
  if (command) return findExecutable(command, env, platform);
  for (const f of bundledCandidates(extensionPath, platform, arch)) {
    if (fs.existsSync(f)) {
      // A .vsix is a zip file, which doesn't always keep the "executable" permission.
      if (platform !== "win32") {
        try {
          fs.accessSync(f, fs.constants.X_OK);
        } catch {
          try {
            fs.chmodSync(f, 0o755);
          } catch {
            /* read-only install; fall through to the error below */
          }
        }
      }
      return f;
    }
  }
  return findExecutable("mbot2", env, platform);
}

/** Parse `mbot2 scan --json` output. Throws on anything unexpected. */
function parseScan(stdout) {
  const data = JSON.parse(stdout.trim().split(/\r?\n/).pop() || "[]");
  if (!Array.isArray(data)) throw new Error("unexpected scan output");
  return data.map((r) => ({
    address: String(r.address),
    name: String(r.name),
    rssi: Number(r.rssi),
    lastUsed: Boolean(r.last_used),
  }));
}

function signalBars(rssi) {
  const level = rssi >= -55 ? 4 : rssi >= -67 ? 3 : rssi >= -78 ? 2 : 1;
  return "▮".repeat(level) + "▯".repeat(4 - level);
}

/** Last-used robot first (so Enter picks it, like the CLI), the rest by signal strength. */
function orderRobots(robots) {
  return [...robots].sort((a, b) => (b.lastUsed - a.lastUsed) || (b.rssi - a.rssi));
}

/** Arguments for the upload command. */
function uploadArgs({ device, file, monitor, verbose }) {
  const args = [];
  if (verbose) args.push("-v");
  args.push("-d", device, "upload", file);
  if (monitor) args.push("--monitor");
  return args;
}

module.exports = { findExecutable, bundledCandidates, resolveMbot2, parseScan, signalBars, orderRobots, uploadArgs };
