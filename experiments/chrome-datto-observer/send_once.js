"use strict";
/*
 * J-Assist one-click governed send coordinator.
 *
 * Production sender/readiness must be independently verified; never replace
 * them with a browser-supplied token or an HTTP endpoint from the active tab.
 * Only the background worker is allowed to invoke this function.
 */
const MAX_JPEG_BYTES=1024*1024;
const SHA256_HEX=/^[0-9a-f]{64}$/;
const ID=/^[a-zA-Z0-9_-]{12,128}$/;
const DATTO_UID=/^(?:[0-9]{1,24}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/;
const safeError=message=>({ok:false,sent:false,error:message});
function isReceipt(result, context, sha256) {
  return result && result.status==="accepted" && result.analyzed_by_model===false &&
    result.session_id===context.sessionId &&
    result.device_uid===context.deviceUid &&
    result.image_sha256===sha256 &&
    typeof result.receipt_id==="string" && ID.test(result.receipt_id);
}
async function sendOnce({getContext,checkReadiness,capture,deliver,isCurrent,digest,now=()=>Date.now()}) {
  // The preflight MUST run before capture: no security permission means no image.
  let context;
  try {
    context=await getContext();
    if (!context || !context.technicianVerified || !context.dattoPermissionVerified ||
        !context.sessionAuthorized || typeof context.deviceUid!=="string" ||
        !DATTO_UID.test(context.deviceUid) ||
        typeof context.sessionId!=="string" || !ID.test(context.sessionId) ||
        !Number.isFinite(context.expiresAt) || context.expiresAt<=now() ||
        context.transport!=="authenticated-https" || context.imageReviewReady!==true) {
      return safeError("Authenticated Jason/Datto send session is unavailable.");
    }
    if (!(await checkReadiness(context))) return safeError("Jason image intake is not ready.");
    if (!(await isCurrent(context))) return safeError("Datto tab is no longer active.");
    const result=await capture(context);
    if (!result || typeof result.image!=="string" ||
        !result.image.startsWith("data:image/jpeg;base64,")) {
      return safeError("Could not capture a valid Datto screenshot.");
    }
    const base64=result.image.slice("data:image/jpeg;base64,".length);
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(base64)) return safeError("Invalid screenshot encoding.");
    const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
    if (!bytes.length || bytes.length>MAX_JPEG_BYTES ||
        bytes[0]!==0xff || bytes[1]!==0xd8 ||
        bytes[bytes.length-2]!==0xff || bytes[bytes.length-1]!==0xd9) {
      return safeError("Screenshot is unsupported or too large.");
    }
    if (!(await isCurrent(context))) return safeError("Datto tab changed during capture.");
    if (context.expiresAt<=now()) return safeError("Jason session expired.");
    const sha256=await digest(bytes);
    if (typeof sha256!=="string" || !SHA256_HEX.test(sha256)) {
      return safeError("Screenshot integrity check failed.");
    }
    // The transport owns the authenticated identity and confidential token.
    // Never include a caller-supplied credential from the Datto tab or panel.
    const resultReceipt=await deliver({context,image:bytes,sha256});
    if (!isReceipt(resultReceipt,context,sha256)) {
      return safeError("Jason did not provide a matching verified receipt.");
    }
    // Revocation/navigation during the upload must never report "Sent".
    if (!(await isCurrent(context))) return safeError("Datto session ended before confirmation.");
    return {ok:true,sent:true,receipt_id:resultReceipt.receipt_id,
            device_uid:context.deviceUid,image_sha256:sha256,
            analyzed_by_model:false};
  } catch {
    return safeError("Send to Jason failed. Nothing was confirmed as received.");
  }
}
const JAssistOneClick=Object.freeze({sendOnce,isReceipt});
if(typeof globalThis!=="undefined")globalThis.JAssistOneClick=JAssistOneClick;
if (typeof module!=="undefined"&&module.exports)module.exports=JAssistOneClick;
