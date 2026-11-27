import { parseApprovalSubmit } from "./approval-submit.mjs";

// References come from genuine provider sends, never editable card values.
export function recordIssuedApprovalCard({ store, card, tenantId, aadObjectId, conversationId, messageId }) {
  if (!Array.isArray(card?.actions) || card.actions.length < 1 || !conversationId || !messageId
      || messageId.startsWith("accepted:")) return false;
  const submits = card.actions.map(action => parseApprovalSubmit(action?.data));
  if (submits.some(submit => !submit) || new Set(submits.map(s => s.approvalId)).size !== 1) return false;
  store.registerIssuedCard({ tenantId, aadObjectId, conversationId, messageId,
                             approvalId: submits[0].approvalId });
  return true;
}

export function canonicalDecision(result, approvalSubmit) {
  const receipt = result?.payload?.approval_decision;
  if (Number(result?.httpStatus ?? 500) >= 400 || !receipt
      || receipt.approval_id !== approvalSubmit.approvalId
      || receipt.decision !== approvalSubmit.decision
      || !["approved", "denied"].includes(receipt.status)
      || (receipt.status === "approved") !== (receipt.decision === "approve")) return null;
  return receipt;
}

export function terminalCard(card) {
  if (card?.type !== "AdaptiveCard" || !Array.isArray(card.body)
      || !Array.isArray(card.actions) || card.actions.length !== 0
      || JSON.stringify(card).length > 28000) throw new Error("terminal approval card invalid");
  // Never preserve a hidden or nested action capable of casting a new vote.
  function check(value) {
    if (!value || typeof value !== "object") return;
    if (value.type === "Action.Submit" || value.type === "Action.Execute") {
      throw new Error("terminal approval card contains a vote");
    }
    for (const nested of Object.values(value)) check(nested);
  }
  check(card);
  return card;
}

export async function updateOriginalApprovalCard({ context, store, tenantId, aadObjectId,
    conversationId, replyToId, approvalSubmit, result }) {
  const receipt = canonicalDecision(result, approvalSubmit);
  if (!receipt?.card || !replyToId) return false;
  const issued = store.issuedCards({ tenantId, aadObjectId, approvalId: approvalSubmit.approvalId });
  if (!issued.some(record => record.messageId === replyToId && record.conversationId === conversationId)) return false;
  await context.updateActivity({ type: "message", id: replyToId,
    text: receipt.status === "approved" ? "Approved" : "Declined",
    attachments: [{ contentType: "application/vnd.microsoft.card.adaptive", content: terminalCard(receipt.card) }] });
  return true;
}


export async function updateIssuedApprovalCards({ adapter, store, proactiveRecord,
    tenantId, aadObjectId, approvalId, status, card }) {
  if (!["approved","denied","replaced"].includes(status) || proactiveRecord?.tenantId?.toLowerCase() !== tenantId.toLowerCase()) {
    throw new Error("terminal approval scope invalid");
  }
  const issued=store.issuedCards({tenantId,aadObjectId,approvalId});
  if (!issued.length) throw new Error("original approval card reference unavailable");
  const content=terminalCard(card);
  const messageIds=[];
  for (const record of issued) {
    const reference={...proactiveRecord.reference,conversation:{...proactiveRecord.reference.conversation,id:record.conversationId}};
    await adapter.continueConversation(proactiveRecord.identity,reference,async ctx=>{
      await ctx.updateActivity({type:"message",id:record.messageId,
        text:typeof content.body[0]?.text === "string" ? content.body[0].text : "Request updated",
        attachments:[{contentType:"application/vnd.microsoft.card.adaptive",content}]});
    });
    messageIds.push(record.messageId);
  }
  return messageIds;
}
