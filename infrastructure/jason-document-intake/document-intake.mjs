/**
 * Jason shared, read-only document intake (PDF v1).
 *
 * Provider callers acquire bytes using their own authenticated connectors.
 * This module never fetches URLs, interprets financial values, or writes to a
 * ledger. It exposes provenance and explicit incompleteness to consumers.
 *
 * Current implementation uses Poppler tools already installed by the Teams
 * gateway container. OCR and page rendering are NOT performed here.
 */
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export class DocumentIntakeError extends Error {
  constructor(code) {
    super(code);
    this.name = "DocumentIntakeError";
    this.code = code;
  }
}

export const DEFAULT_PDF_LIMITS = Object.freeze({
  maxBytes: 6 * 1024 * 1024,
  maxPages: 200,
  maxTextChars: 48_000,
  maxDownloadBytes: 6 * 1024 * 1024,
});

function positiveLimit(value, name) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new TypeError(name + " must be a positive integer");
  }
  return value;
}

function command(program, args, { timeoutMs, maxOutputBytes }) {
  try {
    return execFileSync(program, args, {
      encoding: "utf8",
      timeout: timeoutMs,
      maxBuffer: maxOutputBytes,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch {
    // No user document content, passwords or tool stderr in error details.
    throw new DocumentIntakeError("pdf_preflight_tool_failed");
  }
}

function pageImageCounts(list, pages) {
  const counts = Array.from({ length: pages }, () => 0);
  for (const line of list.split(/\r?\n/)) {
    // pdfimages -list prints columns "page num type width ..."
    const match = line.match(/^\s*(\d+)\s+\d+\s+(?:image|mask|smask|stencil)\s+/i);
    if (match) {
      const page = Number(match[1]);
      if (page >= 1 && page <= pages) counts[page - 1] += 1;
    }
  }
  return counts;
}

/** Validate an already-authorized stream before it is buffered in memory. */
export async function readBoundedResponse(response, maxBytes = DEFAULT_PDF_LIMITS.maxDownloadBytes) {
  positiveLimit(maxBytes, "maxBytes");
  const declared = Number(response?.headers?.get("content-length") ?? 0);
  if (Number.isFinite(declared) && declared > maxBytes) {
    throw new DocumentIntakeError("document_download_size_limit");
  }
  if (!response?.body) throw new DocumentIntakeError("document_download_empty");
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) throw new DocumentIntakeError("document_download_size_limit");
      chunks.push(Buffer.from(value));
    }
    if (total < 1) throw new DocumentIntakeError("document_download_empty");
    return Buffer.concat(chunks, total);
  } catch (error) {
    try { await reader.cancel(); } catch {}
    throw error;
  } finally {
    try { reader.releaseLock(); } catch {}
  }
}

/**
 * Produce a canonical immutable evidence summary. Text is never silently
 * truncated: rejecting oversized extraction is necessary for financial uses.
 *
 * A page marked "has_images" does NOT establish that every visible statement
 * figure was detected. The consumer must render and validate all pages.
 */
export function inspectPdfBuffer(
  bytes,
  {
    maxBytes = DEFAULT_PDF_LIMITS.maxBytes,
    maxPages = DEFAULT_PDF_LIMITS.maxPages,
    maxTextChars = DEFAULT_PDF_LIMITS.maxTextChars,
    requireNativeText = false,
    pageInventory = false,
    runCommand = command,
  } = {},
) {
  positiveLimit(maxBytes, "maxBytes");
  positiveLimit(maxPages, "maxPages");
  positiveLimit(maxTextChars, "maxTextChars");
  if (!Buffer.isBuffer(bytes)) throw new DocumentIntakeError("document_bytes_required");
  if (bytes.length < 5 || bytes.subarray(0, 5).toString("ascii") !== "%PDF-") {
    throw new DocumentIntakeError("document_not_pdf");
  }
  if (bytes.length > maxBytes) throw new DocumentIntakeError("document_size_limit");
  const hash = createHash("sha256").update(bytes).digest("hex");
  const directory = mkdtempSync(join(tmpdir(), "jason-document-intake-"));
  const filepath = join(directory, "source.pdf");
  try {
    writeFileSync(filepath, bytes, { mode: 0o600, flag: "wx" });
    const info = runCommand("pdfinfo", [filepath], {
      timeoutMs: 20_000,
      maxOutputBytes: 256 * 1024,
    });
    const count = info.match(/^Pages:\s*(\d+)\s*$/mi);
    const pages = count ? Number(count[1]) : 0;
    if (!Number.isSafeInteger(pages) || pages < 1 || pages > maxPages) {
      throw new DocumentIntakeError("document_page_limit_or_invalid_count");
    }
    if (/^Encrypted:\s*yes/mi.test(info)) {
      throw new DocumentIntakeError("document_encrypted");
    }
    const imageCounts = pageImageCounts(
      runCommand("pdfimages", ["-list", filepath], {
        timeoutMs: 20_000,
        maxOutputBytes: 512 * 1024,
      }),
      pages,
    );
    const rawText = runCommand("pdftotext", ["-layout", filepath, "-"], {
      timeoutMs: 20_000,
      maxOutputBytes: Math.max(2 * 1024 * 1024, maxTextChars * 4),
    });
    const extractedText = rawText.replace(/\u0000/g, "").trim();
    if (extractedText.length > maxTextChars) {
      throw new DocumentIntakeError("document_text_limit");
    }
    const hasNativeText = Boolean(extractedText);
    const hasImages = imageCounts.some((count) => count > 0);
    if (requireNativeText && !hasNativeText) {
      throw new DocumentIntakeError("document_native_text_required");
    }
    if (!hasNativeText && !hasImages) {
      throw new DocumentIntakeError("document_unreadable");
    }
    const documentKind = hasNativeText && hasImages
      ? "hybrid"
      : hasNativeText ? "native_text" : "scanned";
    const inventory = pageInventory
      ? imageCounts.map((count, index) => ({
          page_number: index + 1,
          image_count: count,
          // Native text per page is intentionally unknown without a
          // page-specific extraction pass.
          native_text_present: null,
        }))
      : [];
    return Object.freeze({
      schema: "jason.document_intake.pdf.v1",
      source_sha256: hash,
      size_bytes: bytes.length,
      page_count: pages,
      document_kind: documentKind,
      has_native_text: hasNativeText,
      has_images: hasImages,
      pages: inventory,
      extracted_text: extractedText,
      extraction_complete: true,
      rendered_verified: false,
      accounting_validated: false,
    });
  } catch (error) {
    if (error instanceof DocumentIntakeError) throw error;
    throw new DocumentIntakeError("document_preflight_failed");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

/**
 * Keep the existing Teams procurement ingress contract unchanged. This is an
 * explicit adapter, not a second PDF extraction implementation.
 */
export function toProcurementDocument(evidence, { name, sourceId = "" }) {
  if (!evidence || evidence.schema !== "jason.document_intake.pdf.v1"
      || !evidence.has_native_text || !evidence.extraction_complete) {
    throw new DocumentIntakeError("document_procurement_not_ready");
  }
  const cleanName = String(name ?? "").trim();
  if (!cleanName || cleanName.length > 255 || !cleanName.toLowerCase().endsWith(".pdf")) {
    throw new DocumentIntakeError("document_filename_invalid");
  }
  const cleanSourceId = String(sourceId ?? "").trim();
  if (cleanSourceId.length > 256) throw new DocumentIntakeError("document_source_id_limit");
  return {
    name: cleanName,
    content_type: "application/pdf",
    size: evidence.size_bytes,
    sha256: evidence.source_sha256,
    extracted_text: evidence.extracted_text,
    source_id: cleanSourceId,
  };
}
