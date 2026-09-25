import { randomUUID } from "node:crypto";

export function resolveProactiveSendResult({ result, isCard, receiptFactory = randomUUID }) {
  const providerMessageId =
    typeof result?.id === "string" && result.id
      ? result.id
      : typeof result?.resourceResponse?.id === "string" && result.resourceResponse.id
        ? result.resourceResponse.id
        : null;

  if (providerMessageId) {
    return {
      messageId: providerMessageId,
      evidenceType: "provider_message_id",
      synthetic: false,
    };
  }

  if (!isCard) return null;

  return {
    messageId: `accepted:${receiptFactory()}`,
    evidenceType: "provider_call_completed_without_message_id",
    synthetic: true,
  };
}
