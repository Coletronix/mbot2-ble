// mBot2 upload button for VS Code. Runs the `mbot2` CLI: the standalone copy bundled under
// bin/ by the release build, or one installed separately.
"use strict";

const vscode = require("vscode");
const { execFile } = require("child_process");
const path = require("path");
const { resolveMbot2, parseScan, signalBars, orderRobots, uploadArgs } = require("./lib");

const TERMINAL_NAME = "mBot2";
const PINNED_KEY = "mbot2.pinnedRobot"; // per-workspace "always use this robot"
const PROJECT_URL = "https://github.com/Coletronix/mbot2-ble#readme";

let statusItem;

function activate(context) {
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  statusItem.command = "mbot2.unpinRobot";
  context.subscriptions.push(
    statusItem,
    vscode.commands.registerCommand("mbot2.upload", (uri) => upload(context, uri)),
    vscode.commands.registerCommand("mbot2.monitor", () => monitor(context)),
    vscode.commands.registerCommand("mbot2.stop", () => stopTerminal()),
    vscode.commands.registerCommand("mbot2.unpinRobot", () => unpin(context)),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("mbot2")) updateStatus(context);
    }),
  );
  updateStatus(context);
}

function config() {
  return vscode.workspace.getConfiguration("mbot2");
}

// ------------------------------------------------------------------ robot choice

/** The robot to use without asking: the `mbot2.device` setting, else one pinned in this
 * workspace. Never "whatever is in range": in a classroom that may be someone else's robot. */
function fixedRobot(context) {
  const setting = (config().get("device") || "").trim();
  if (setting) return { address: setting, name: setting, source: "setting" };
  const pinned = context.workspaceState.get(PINNED_KEY);
  return pinned ? { ...pinned, source: "pinned" } : null;
}

function updateStatus(context) {
  const r = fixedRobot(context);
  if (!r) return statusItem.hide();
  statusItem.text = `$(pinned) ${r.name}`;
  statusItem.tooltip =
    r.source === "setting"
      ? `mBot2 uploads go to ${r.name} (the mbot2.device setting). Click to change.`
      : `mBot2 uploads go to ${r.name} without asking. Click to ask every time again.`;
  statusItem.show();
}

async function unpin(context) {
  const r = fixedRobot(context);
  if (r && r.source === "setting") {
    return vscode.commands.executeCommand("workbench.action.openSettings", "mbot2.device");
  }
  await context.workspaceState.update(PINNED_KEY, undefined);
  updateStatus(context);
  vscode.window.showInformationMessage("mBot2: you'll be asked which robot to use on each upload.");
}

function scanRobots(exe, seconds) {
  return new Promise((resolve, reject) => {
    execFile(exe, ["scan", "--json", "-t", String(seconds)], { timeout: (seconds + 20) * 1000 }, (err, stdout, stderr) => {
      if (err) {
        const msg = (stderr || "").trim().split(/\r?\n/).pop() || err.message;
        return reject(new Error(msg));
      }
      try {
        resolve(parseScan(stdout));
      } catch (e) {
        reject(new Error(`Couldn't read the robot list (${e.message}). Is the mbot2 tool up to date?`));
      }
    });
  });
}

/** Ask which robot to use, in a quick pick that fills in after a Bluetooth scan.
 * Resolves to {address, name} or undefined if cancelled. */
function pickRobot(context, exe) {
  const seconds = config().get("scanSeconds") || 4;
  const pinButton = { iconPath: new vscode.ThemeIcon("pin"), tooltip: "Always use this robot in this workspace (skip this list)" };
  const rescanItem = { label: "$(refresh) Scan again", alwaysShow: true, rescan: true };

  return new Promise((resolve) => {
    const qp = vscode.window.createQuickPick();
    qp.title = "Upload to which mBot2?";
    qp.matchOnDescription = true;
    qp.ignoreFocusOut = true;
    let done = false;
    const finish = (value) => {
      if (done) return;
      done = true;
      resolve(value);
      qp.dispose();
    };

    const scan = async () => {
      qp.busy = true;
      qp.items = [];
      qp.placeholder = "Scanning for robots…";
      try {
        const robots = orderRobots(await scanRobots(exe, seconds));
        if (done) return;
        if (!robots.length) {
          qp.placeholder = "No robots found. Is yours switched on (battery switch) and not connected to mBlock?";
          qp.items = [rescanItem];
        } else {
          qp.placeholder = "Check the name printed on the side of YOUR robot (type the last few characters to filter)";
          qp.items = [
            ...robots.map((r) => ({
              label: r.name,
              description: `${signalBars(r.rssi)}  ${r.address}`,
              detail: r.lastUsed ? "$(history) last used on this computer (Enter picks it)" : undefined,
              buttons: [pinButton],
              robot: r,
            })),
            rescanItem,
          ];
          // Like the CLI: Enter reuses the last robot, but only if it's in range right now.
          qp.activeItems = robots[0].lastUsed ? [qp.items[0]] : [];
        }
      } catch (e) {
        if (done) return;
        finish(undefined);
        showCliError(e.message);
      } finally {
        qp.busy = false;
      }
    };

    qp.onDidAccept(() => {
      const item = qp.selectedItems[0] || qp.activeItems[0];
      if (!item) return;
      if (item.rescan) return void scan();
      finish({ address: item.robot.address, name: item.robot.name });
    });
    qp.onDidTriggerItemButton(async ({ item }) => {
      const robot = { address: item.robot.address, name: item.robot.name };
      await context.workspaceState.update(PINNED_KEY, robot);
      updateStatus(context);
      finish(robot);
    });
    qp.onDidHide(() => finish(undefined));
    qp.show();
    scan();
  });
}

/** Resolves to {address, name} or undefined. */
async function choose(context, exe) {
  const fixed = fixedRobot(context);
  if (fixed) return fixed;
  await stopTerminal(); // a running monitor holds the robot's only Bluetooth connection; free it to scan
  return pickRobot(context, exe);
}

// ------------------------------------------------------------------ terminal

/** Stop whatever the mBot2 terminal is running. Ctrl-C first, so the tool disconnects cleanly:
 * killed outright, it can leave the robot connected (BlueZ keeps the link), and then it
 * neither shows up in a scan nor accepts a new connection. */
async function stopTerminal() {
  const terms = vscode.window.terminals.filter((t) => t.name === TERMINAL_NAME);
  for (const t of terms) if (t.exitStatus === undefined) t.sendText("\x03", false);
  const deadline = Date.now() + 3000;
  while (terms.some((t) => t.exitStatus === undefined) && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 100));
  }
  for (const t of terms) t.dispose();
}

async function runInTerminal(exe, args, cwd) {
  await stopTerminal();
  const term = vscode.window.createTerminal({
    name: TERMINAL_NAME,
    shellPath: exe,
    shellArgs: args,
    cwd,
    iconPath: new vscode.ThemeIcon("hubot"),
    env: { PYTHONUNBUFFERED: "1" },
  });
  term.show(true);
  return term;
}

async function mbot2Executable(context) {
  const command = (config().get("command") || "").trim();
  const exe = resolveMbot2(command, context.extensionPath);
  if (exe) return exe;
  const message = command
    ? `mBot2: couldn't find \`${command}\` (the mbot2.command setting). Fix the path, or clear the setting to use the copy built into this extension.`
    : `mBot2: this extension has no built-in uploader for this computer (${process.platform}-${process.arch}). ` +
      "Install the mbot2 command-line tool (see the project page), or set its path in the mbot2.command setting.";
  const pick = await vscode.window.showErrorMessage(message, "Open Settings", "Project Page");
  if (pick === "Open Settings") vscode.commands.executeCommand("workbench.action.openSettings", "mbot2.command");
  if (pick === "Project Page") vscode.env.openExternal(vscode.Uri.parse(PROJECT_URL));
  return null;
}

function showCliError(message) {
  vscode.window.showErrorMessage(`mBot2: ${message}`);
}

// ------------------------------------------------------------------ commands

async function upload(context, uri) {
  // From the editor title button VS Code passes the file's URI; from the palette, use the active editor.
  let doc;
  if (uri instanceof vscode.Uri) {
    doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
  } else {
    doc = vscode.window.activeTextEditor && vscode.window.activeTextEditor.document;
    uri = doc && doc.uri;
  }
  if (!uri) return showCliError("open the Python file you want to upload first.");
  if (doc && doc.isUntitled) {
    if (!(await doc.save())) return;
    uri = doc.uri;
  }
  if (uri.scheme !== "file") return showCliError("only files saved on this computer can be uploaded.");
  if (doc && doc.isDirty && !(await doc.save())) return;

  const exe = await mbot2Executable(context);
  if (!exe) return;
  const robot = await choose(context, exe);
  if (!robot) return;

  const file = uri.fsPath;
  await runInTerminal(
    exe,
    uploadArgs({
      device: robot.address,
      file,
      monitor: config().get("monitorAfterUpload"),
      verbose: config().get("verbose"),
    }),
    path.dirname(file),
  );
}

async function monitor(context) {
  const exe = await mbot2Executable(context);
  if (!exe) return;
  const robot = await choose(context, exe);
  if (!robot) return;
  const args = config().get("verbose") ? ["-v"] : [];
  await runInTerminal(exe, [...args, "-d", robot.address, "monitor"]);
}

function deactivate() {}

module.exports = { activate, deactivate };
