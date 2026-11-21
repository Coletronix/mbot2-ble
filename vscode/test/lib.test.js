"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { findExecutable, parseScan, signalBars, orderRobots, uploadArgs } = require("../lib");

test("parseScan reads mbot2 scan --json", () => {
  const out = '[{"address": "AA:BB", "name": "Makeblock_LE1", "rssi": -60, "last_used": true}]\n';
  assert.deepStrictEqual(parseScan(out), [{ address: "AA:BB", name: "Makeblock_LE1", rssi: -60, lastUsed: true }]);
  assert.deepStrictEqual(parseScan("[]"), []);
  assert.throws(() => parseScan("Found 2 robots"));
  assert.throws(() => parseScan('{"a": 1}'));
});

test("orderRobots puts the last-used robot first, then strongest signal", () => {
  const r = (name, rssi, lastUsed = false) => ({ name, rssi, lastUsed });
  const got = orderRobots([r("a", -80), r("b", -50), r("c", -90, true)]).map((x) => x.name);
  assert.deepStrictEqual(got, ["c", "b", "a"]);
});

test("signalBars matches the CLI's thresholds", () => {
  assert.strictEqual(signalBars(-50), "▮▮▮▮");
  assert.strictEqual(signalBars(-70), "▮▮▯▯");
  assert.strictEqual(signalBars(-95), "▮▯▯▯");
});

test("uploadArgs", () => {
  assert.deepStrictEqual(uploadArgs({ device: "AA", file: "/x/p.py", monitor: true, verbose: false }),
    ["-d", "AA", "upload", "/x/p.py", "--monitor"]);
  assert.deepStrictEqual(uploadArgs({ device: "AA", file: "p.py", monitor: false, verbose: true }),
    ["-v", "-d", "AA", "upload", "p.py"]);
});

test("findExecutable searches PATH and honours PATHEXT on Windows", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mbot2-"));
  const exe = path.join(dir, "mbot2");
  fs.writeFileSync(exe, "#!/bin/sh\n");
  fs.chmodSync(exe, 0o755);
  if (process.platform !== "win32") {
    assert.strictEqual(findExecutable("mbot2", { PATH: dir }), exe);
    assert.strictEqual(findExecutable(exe, { PATH: "" }), exe);
  }
  const winDir = fs.mkdtempSync(path.join(os.tmpdir(), "mbot2-win-"));
  fs.writeFileSync(path.join(winDir, "mbot2.EXE"), "");
  assert.strictEqual(findExecutable("mbot2", { PATH: winDir, PATHEXT: ".EXE;.CMD" }, "win32"), path.join(winDir, "mbot2.EXE"));
  assert.strictEqual(findExecutable("definitely-not-a-program-xyz", { PATH: dir }), null);
});
