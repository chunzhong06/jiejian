// 用真实 TypeScript Server 验证正式前端源码能够从 var 受控工作区解析依赖。

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { spawn } = require("node:child_process");

const [workspaceArg, projectRootArg, varDirArg] = process.argv.slice(2);
if (!workspaceArg || !projectRootArg || !varDirArg) {
  throw new Error("frontend editor verification requires workspace, project root, and var dir");
}

const workspace = path.resolve(workspaceArg);
const projectRoot = path.resolve(projectRootArg);
const varDir = path.resolve(varDirArg);
const tsserver = path.join(workspace, "node_modules", "typescript", "lib", "tsserver.js");
const plugin = path.join(
  workspace,
  "node_modules",
  "jiejian-controlled-workspace-resolver",
  "package.json",
);
const files = [
  path.join(
    projectRoot,
    "product",
    "frontend",
    "src",
    "features",
    "checks",
    "CheckHistoryPage.tsx",
  ),
  path.join(
    projectRoot,
    "product",
    "frontend",
    "src",
    "features",
    "checks",
    "StartCheckPage.test.tsx",
  ),
];

for (const required of [tsserver, plugin, ...files]) {
  if (!fs.statSync(required, { throwIfNoEntry: false })?.isFile()) {
    throw new Error(`frontend editor verification input is missing: ${required}`);
  }
}

const tempDir = path.join(varDir, "temp");
fs.mkdirSync(tempDir, { recursive: true });
const logPath = path.join(tempDir, `tsserver-editor-${randomUUID()}.log`);
const child = spawn(
  process.execPath,
  [tsserver, "--logVerbosity", "verbose", "--logFile", logPath],
  { cwd: projectRoot, stdio: ["pipe", "pipe", "pipe"] },
);

let output = Buffer.alloc(0);
let stderr = "";
const responses = new Map();
let completed = false;

function fail(message) {
  if (completed) return;
  completed = true;
  child.kill();
  throw new Error(message);
}

function consumeOutput(chunk) {
  output = Buffer.concat([output, chunk]);
  while (true) {
    const separator = output.indexOf("\r\n\r\n");
    if (separator < 0) return;
    const header = output.subarray(0, separator).toString("utf8");
    const lengthMatch = /Content-Length:\s*(\d+)/i.exec(header);
    if (!lengthMatch) fail("TypeScript Server returned an invalid frame");
    const length = Number(lengthMatch[1]);
    const bodyStart = separator + 4;
    if (output.length < bodyStart + length) return;
    const body = output.subarray(bodyStart, bodyStart + length).toString("utf8");
    output = output.subarray(bodyStart + length);
    const message = JSON.parse(body);
    if (message.type === "response") responses.set(message.request_seq, message);
  }
}

child.stdout.on("data", consumeOutput);
child.stderr.on("data", (chunk) => {
  stderr += chunk.toString("utf8");
});

let sequence = 0;
const diagnosticRequests = [];
for (const file of files) {
  child.stdin.write(
    `${JSON.stringify({
      seq: ++sequence,
      type: "request",
      command: "open",
      arguments: { file, projectRootPath: projectRoot },
    })}\n`,
  );
  const diagnosticSequence = ++sequence;
  diagnosticRequests.push(diagnosticSequence);
  child.stdin.write(
    `${JSON.stringify({
      seq: diagnosticSequence,
      type: "request",
      command: "semanticDiagnosticsSync",
      arguments: { file },
    })}\n`,
  );
}

const deadline = setTimeout(() => {
  child.stdin.end();
}, 15_000);

const poll = setInterval(() => {
  if (!diagnosticRequests.every((request) => responses.has(request))) return;
  clearInterval(poll);
  clearTimeout(deadline);
  child.stdin.end();
}, 25);

child.on("exit", (code) => {
  clearInterval(poll);
  clearTimeout(deadline);
  try {
    if (code !== 0) throw new Error(`TypeScript Server exited with ${code}: ${stderr.trim()}`);
    const log = fs.readFileSync(logPath, "utf8");
    if (!log.includes("Plugin validation succeeded")) {
      throw new Error("TypeScript Server did not load the controlled workspace resolver");
    }
    for (const request of diagnosticRequests) {
      const response = responses.get(request);
      if (!response?.success || !Array.isArray(response.body) || response.body.length) {
        throw new Error(`frontend source diagnostics remain: ${JSON.stringify(response?.body ?? response)}`);
      }
    }
    completed = true;
    process.stdout.write("TypeScript 编辑器依赖解析通过。\n");
  } finally {
    fs.rmSync(logPath, { force: true });
  }
});
