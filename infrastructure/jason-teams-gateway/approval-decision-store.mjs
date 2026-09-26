import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

function load(path) {
  if (!existsSync(path)) return {};
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    throw new Error("Teams approval decision store is unreadable");
  }
}

function save(path, records) {
  mkdirSync(dirname(path), { recursive: true });
  const temp = `${path}.tmp-${process.pid}`;
  writeFileSync(temp, JSON.stringify(records), { mode: 0o600 });
  renameSync(temp, path);
}

function keyFor(tenantId, approvalId) {
  return `${tenantId.toLowerCase()}:${approvalId}`;
}

export function createApprovalDecisionStore({ path, now = () => new Date() }) {
  if (!path || typeof path !== "string") throw new Error("approval decision store path is required");

  return {
    begin({ tenantId, approvalId, aadObjectId, decision, messageId }) {
      const records = load(path);
      const key = keyFor(tenantId, approvalId);
      const existing = records[key];
      if (existing) return { accepted: false, record: existing };
      const record = {
        tenantId,
        approvalId,
        aadObjectId,
        decision,
        state: "processing",
        messageId,
        startedAt: now().toISOString(),
      };
      records[key] = record;
      save(path, records);
      return { accepted: true, record };
    },
    release({ tenantId, approvalId, aadObjectId, decision }) {
      const records = load(path);
      const key = keyFor(tenantId, approvalId);
      const current = records[key];
      if (!current) return null;
      if (current.state !== "processing") return current;
      if (current.aadObjectId !== aadObjectId || current.decision !== decision) {
        throw new Error("approval decision release scope mismatch");
      }
      delete records[key];
      save(path, records);
      return null;
    },

    finalize({ tenantId, approvalId, resultStatus }) {
      const records = load(path);
      const key = keyFor(tenantId, approvalId);
      const current = records[key];
      if (!current) throw new Error("approval decision was not claimed");
      if (current.state === "decided") return current;
      const decided = {
        ...current,
        state: "decided",
        resultStatus,
        decidedAt: now().toISOString(),
      };
      records[key] = decided;
      save(path, records);
      return decided;
    },

    get({ tenantId, approvalId }) {
      return load(path)[keyFor(tenantId, approvalId)] ?? null;
    },
  };
}
