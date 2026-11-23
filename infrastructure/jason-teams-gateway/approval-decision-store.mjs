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
    beginSend({ tenantId, aadObjectId, communicationId, payloadDigest }) {
      if (!/^comm-[a-f0-9]{64}$/.test(communicationId) || !/^[a-f0-9]{64}$/.test(payloadDigest)) {
        throw new Error("invalid communication claim");
      }
      const records=load(path);
      const key=`send:${tenantId.toLowerCase()}:${aadObjectId.toLowerCase()}:${communicationId}`;
      const current=records[key];
      if (current) {
        if (current.payloadDigest !== payloadDigest) throw new Error("communication scope changed");
        return { accepted:false, record:current };
      }
      const record={ state:"processing", payloadDigest, startedAt:now().toISOString() };
      records[key]=record;save(path,records);
      return { accepted:true, record };
    },
    completeSend({ tenantId, aadObjectId, communicationId, result }) {
      const records=load(path);
      const key=`send:${tenantId.toLowerCase()}:${aadObjectId.toLowerCase()}:${communicationId}`;
      if (records[key]?.state !== "processing" || !result?.message_id) throw new Error("communication claim missing");
      records[key]={...records[key],state:"provider_accepted",result};save(path,records);
    },
    sendReceipt({ tenantId, aadObjectId, communicationId }) {
      if (!/^comm-[a-f0-9]{64}$/.test(communicationId)) throw new Error("invalid communication reference");
      const record=load(path)[`send:${tenantId.toLowerCase()}:${aadObjectId.toLowerCase()}:${communicationId}`];
      return record ?? null;
    },
    registerIssuedCard({ tenantId, approvalId, aadObjectId, conversationId, messageId }) {
      if (![tenantId, approvalId, aadObjectId, conversationId, messageId].every(
          value => typeof value === "string" && value.length > 0 && value.length <= 512)
          || messageId.startsWith("accepted:")) throw new Error("real issued card scope required");
      const records = load(path);
      const key = `issued:${keyFor(tenantId, approvalId)}:${aadObjectId.toLowerCase()}:${messageId}`;
      const record = { tenantId, approvalId, aadObjectId, conversationId, messageId };
      if (records[key] && JSON.stringify(records[key]) !== JSON.stringify(record)) {
        throw new Error("issued card scope changed");
      }
      records[key] = record;
      save(path, records);
      return record;
    },
    issuedCards({ tenantId, approvalId, aadObjectId }) {
      const prefix = `issued:${keyFor(tenantId, approvalId)}:${aadObjectId.toLowerCase()}:`;
      return Object.entries(load(path)).filter(([key]) => key.startsWith(prefix)).map(([,value]) => value);
    },
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
