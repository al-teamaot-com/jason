// Strict Teams-channel identity evidence for approval card submissions.
// This is a prerequisite inside the SDK-authenticated activity handler,
// NOT user OAuth/SSO proof or permission to execute anything.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const isUuid = (value) => typeof value === "string" && UUID_RE.test(value.trim());

export function isBoundTeamsApprovalActivity({ activity, expectedTenantId }) {
  if (activity?.channelId !== "msteams") return false;
  const tenantId = activity?.channelData?.tenant?.id;
  const objectId = activity?.from?.aadObjectId;
  if (!isUuid(expectedTenantId) || !isUuid(tenantId) || !isUuid(objectId)) return false;
  if (tenantId.toLowerCase() !== expectedTenantId.toLowerCase()) return false;
  if (typeof activity?.conversation?.id !== "string" || !activity.conversation.id.trim()) return false;
  if (typeof activity?.id !== "string" || !activity.id.trim()) return false;
  return true;
}
