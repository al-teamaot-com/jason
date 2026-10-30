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

// Teams splits an activity containing both text and card attachments into two
// messages and may return an empty HTTP 202. Send one attachment-only message
// so its provider response can identify the actual card. Summary is metadata,
// not a second visible text activity; card rendering and button data stay exact.
// Reference: microsoft/botframework-sdk#6155.
export function buildProactiveActivity(text, card) {
  return card
    ? {
        type: "message",
        summary: text,
        attachments: [
          {
            contentType: "application/vnd.microsoft.card.adaptive",
            content: card,
          },
        ],
      }
    : text;
}
