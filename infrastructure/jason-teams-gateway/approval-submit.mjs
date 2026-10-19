// Pure approval-submit parsing shared by the gateway and cross-language card tests.
// No caller-supplied principal, tenant, capability or token may assert authority.
function nonBlank(value) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export function parseApprovalSubmit(value) {
  if (!value || typeof value !== "object") return null;
  const approvalId = nonBlank(value.approval_id);
  const decision = nonBlank(value.decision)?.toLowerCase();
  if (!approvalId || approvalId.length > 256 || !["approve", "deny", "request_changes"].includes(decision)) {
    return null;
  }

  const forbidden = new Set([
    "principal_id", "organization_id", "client_id", "capability",
    "capability_name", "provider", "provider_id", "connector",
    "connector_id", "authority_context_id", "requested_by",
    "token", "access_token", "id_token", "refresh_token",
    "authorization", "bearer", "sso_token",
  ]);
  const selections = {};
  for (const [key, raw] of Object.entries(value)) {
    if (key === "approval_id" || key === "decision") continue;
    if (forbidden.has(key)) return null;
    if (!/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(key)) return null;
    if (Object.keys(selections).length >= 32) return null;
    if (!["string", "number", "boolean"].includes(typeof raw)) return null;
    const normalized = String(raw).trim();
    if (normalized.length > 512) return null;
    selections[key] = normalized;
  }
  return { approvalId, decision, selections };
}
