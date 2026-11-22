// Presentation routing only. The original signed envelope remains authoritative.
export function objectiveApprovalRuntimeUrl({ approvalId, runtimeUrl, objectiveUrl }) {
  if (typeof approvalId !== "string" ||
      !approvalId.startsWith("planapproval-objective-")) {
    return runtimeUrl;
  }
  if (!/^planapproval-objective-[0-9a-f]{32}$/.test(approvalId)) {
    throw new Error("Invalid bounded objective approval identifier");
  }
  if (typeof objectiveUrl !== "string" || !objectiveUrl.trim()) {
    throw new Error("The governed objective approval route is not active");
  }
  const url = new URL(objectiveUrl);
  if (url.protocol !== "http:" || url.hostname !== "jason-owner-objective" ||
      url.port !== "8097" || url.pathname !== "/v1/openclaw/teams/conversation" ||
      url.username || url.password || url.search || url.hash) {
    throw new Error("The governed objective approval route is not registered");
  }
  return url.href;
}
