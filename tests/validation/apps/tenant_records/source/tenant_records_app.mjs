// 第二验证应用：用真实多租户记录读写和授权变更生成可观察业务事实，不保存任何 oracle 答案。

import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { join, resolve } from "node:path";


const argumentsMap = new Map(
  process.argv.slice(2).map((item) => {
    const separator = item.indexOf("=");
    return separator > 2
      ? [item.slice(2, separator), item.slice(separator + 1)]
      : [item.slice(2), ""];
  }),
);
const stateDir = resolve(argumentsMap.get("state-dir") || ".");
const readyFile = resolve(argumentsMap.get("ready-file") || join(stateDir, "ready.json"));
const breakMode = argumentsMap.get("mode");
const implementation = argumentsMap.get("implementation");
const observationMode = argumentsMap.get("observation");
if (
  ![
    "object_tenant_check_missing",
    "new_entry_inheritance",
    "feature_authorization_bypass",
    "delegation_authority_expansion",
    "deny_async_consequence",
  ].includes(breakMode) ||
  !["MODE_FAULT_PRESENT", "MODE_GUARD_ACTIVE"].includes(implementation) ||
  !["AVAILABLE", "UNAVAILABLE"].includes(observationMode)
) {
  throw new Error("invalid validation state selector");
}

mkdirSync(stateDir, { recursive: true });
const eventPath = join(stateDir, "events.jsonl");
let records;
let members;
let events;

function resetState() {
  records = new Map([
    [
      "record-owner",
      {
        record_id: "record-owner",
        tenant_id: "tenant-alpha",
        project_id: "project-alpha",
        owner_id: "owner",
        title: "负责人记录",
        content: "仅限项目负责人查看",
      },
    ],
    [
      "record-new",
      {
        record_id: "record-new",
        tenant_id: "tenant-alpha",
        project_id: "project-alpha",
        owner_id: "owner",
        title: "新建项目记录",
        content: "应继承项目负责人权限",
      },
    ],
  ]);
  members = new Set(["owner", "member"]);
  events = [];
  writeFileSync(eventPath, "", "utf8");
}

function recordEvent(caseId, kind, semanticKey, identity, decision = null) {
  const event = {
    sequence: events.length + 1,
    case_id: caseId,
    kind,
    semantic_key: semanticKey,
    identity,
    authorization_decision: decision,
  };
  events.push(event);
  appendFileSync(eventPath, `${JSON.stringify(event)}\n`, "utf8");
}

function send(response, status, payload) {
  const body = Buffer.from(JSON.stringify(payload));
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": body.length,
  });
  response.end(body);
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  if (chunks.length === 0) {
    return {};
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function actionFor(method, path) {
  if (method === "GET" && path === "/api/projects/project-alpha/records/record-owner") {
    return "read_record";
  }
  if (
    method === "PATCH" &&
    [
      "/api/projects/project-alpha/records/record-owner",
      "/api/projects/project-alpha/records/record-new",
    ].includes(path)
  ) {
    return "modify_record";
  }
  if (method === "POST" && path === "/api/projects/project-alpha/members") {
    return "grant_authority";
  }
  return null;
}

function applyEffect(action, payload, caseId, identity, targetRecord) {
  if (action === "read_record") {
    recordEvent(caseId, "PROTECTED_EFFECT", "record_disclosed", identity);
    return { record: records.get("record-owner") };
  }
  if (action === "modify_record") {
    const current = records.get(targetRecord);
    records.set(targetRecord, { ...current, title: payload.title || "已修改记录" });
    recordEvent(caseId, "PROTECTED_EFFECT", "record_modified", identity);
    return { record: records.get(targetRecord) };
  }
  members.add(payload.member_id || "invited-member");
  recordEvent(caseId, "PROTECTED_EFFECT", "authority_granted", identity);
  return { members: [...members].sort() };
}

resetState();
const server = createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/health") {
    send(response, 200, { schema_version: "1", status: "ready" });
    return;
  }
  if (request.method === "POST" && url.pathname === "/_validation/reset") {
    resetState();
    send(response, 200, { schema_version: "1", status: "reset" });
    return;
  }
  if (request.method === "GET" && url.pathname === "/_validation/observations") {
    if (observationMode === "UNAVAILABLE") {
      send(response, 503, { schema_version: "1", code: "OBSERVATION_UNAVAILABLE" });
      return;
    }
    const caseId = url.searchParams.get("case_id");
    send(response, 200, {
      schema_version: "1",
      events: events.filter((item) => item.case_id === caseId),
    });
    return;
  }

  const action = actionFor(request.method, url.pathname);
  if (action === null) {
    send(response, 404, { schema_version: "1", code: "NOT_FOUND" });
    return;
  }
  const identity = request.headers["x-validation-identity"] || "anonymous";
  const caseId = request.headers["x-validation-case-id"] || "case-unknown";
  const targetRecord = url.pathname.endsWith("record-new") ? "record-new" : "record-owner";
  const payload = await readJson(request);
  recordEvent(caseId, "ENTRY", "request_received", identity);
  recordEvent(caseId, "IDENTITY", "identity_resolved", identity);
  const allowed = identity === "owner";
  if (allowed) {
    recordEvent(caseId, "AUTHORIZATION", "authorization_decided", identity, "ALLOW");
    const result = applyEffect(action, payload, caseId, identity, targetRecord);
    send(response, 200, { schema_version: "1", data: result });
    return;
  }
  if (implementation === "MODE_GUARD_ACTIVE") {
    recordEvent(caseId, "AUTHORIZATION", "authorization_decided", identity, "DENY");
    send(response, 403, { schema_version: "1", code: "PERMISSION_DENIED" });
    return;
  }

  if (["object_tenant_check_missing", "new_entry_inheritance"].includes(breakMode)) {
    const result = applyEffect(action, payload, caseId, identity, targetRecord);
    send(response, 200, { schema_version: "1", data: result });
    return;
  }
  recordEvent(caseId, "AUTHORIZATION", "authorization_decided", identity, "DENY");
  if (breakMode === "feature_authorization_bypass") {
    recordEvent(caseId, "FEATURE", "feature_route_bypassed", identity);
    applyEffect(action, payload, caseId, identity, targetRecord);
  } else if (breakMode === "delegation_authority_expansion") {
    recordEvent(caseId, "DELEGATION", "service_authority_expanded", identity);
    applyEffect(action, payload, caseId, "validation-service", targetRecord);
  } else if (breakMode === "deny_async_consequence") {
    recordEvent(caseId, "MESSAGE", "denied_work_dispatched", identity);
    setTimeout(
      () => applyEffect(action, payload, caseId, "validation-worker", targetRecord),
      25,
    );
  }
  send(response, 403, { schema_version: "1", code: "PERMISSION_DENIED" });
});

server.listen(0, "127.0.0.1", () => {
  const address = server.address();
  writeFileSync(
    readyFile,
    JSON.stringify({ schema_version: "1", port: address.port }),
    "utf8",
  );
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
