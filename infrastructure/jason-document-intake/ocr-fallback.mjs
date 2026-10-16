/** Optional, fail-closed OCR adapter for scanned PDF evidence.
 * A separate controlled caller must explicitly enable this adapter.
 * Never treat OCR text as independently verified financial data.
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DocumentIntakeError, DEFAULT_PDF_LIMITS } from "./document-intake.mjs";

function run(program, args, options) {
  try {
    return execFileSync(program, args, {
      encoding: "utf8", timeout: 25000, maxBuffer: 2 * 1024 * 1024,
      windowsHide: true, stdio: ["ignore", "pipe", "pipe"], ...options,
    });
  } catch {
    throw new DocumentIntakeError("document_ocr_tool_unavailable_or_failed");
  }
}

/** Read-only OCR, with explicit page identity and incompleteness.
 * Rendering and OCR are intentionally limited to bounded documents.
 */
export function extractScannedPdfPages(bytes, {
  sourceEvidence, maxPages = 12, maxCharsPerPage = 10000,
  runCommand = run,
} = {}) {
  if (!Buffer.isBuffer(bytes) || bytes.length < 5 ||
      bytes.subarray(0, 5).toString("ascii") !== "%PDF-")
    throw new DocumentIntakeError("document_not_pdf");
  if (!sourceEvidence || sourceEvidence.schema !== "jason.document_intake.pdf.v1" ||
      !Number.isSafeInteger(sourceEvidence.page_count) ||
      sourceEvidence.page_count < 1 || sourceEvidence.page_count > maxPages ||
      sourceEvidence.size_bytes !== bytes.length ||
      !/^[a-f0-9]{64}$/.test(sourceEvidence.source_sha256))
    throw new DocumentIntakeError("document_ocr_invalid_evidence");
  if (bytes.length > DEFAULT_PDF_LIMITS.maxBytes ||
      !Number.isSafeInteger(maxCharsPerPage) || maxCharsPerPage < 1 || maxCharsPerPage > 50000)
    throw new DocumentIntakeError("document_ocr_limits");
  if (!Number.isSafeInteger(maxPages) || maxPages < 1 || maxPages > 50)
    throw new DocumentIntakeError("document_ocr_limits");
  if (createHash("sha256").update(bytes).digest("hex") !== sourceEvidence.source_sha256)
    throw new DocumentIntakeError("document_ocr_source_mismatch");
  const directory = mkdtempSync(join(tmpdir(), "jason-ocr-"));
  try {
    const input = join(directory, "source.pdf");
    writeFileSync(input, bytes, { mode: 0o600, flag: "wx" });
    const pages = [];
    for (let page = 1; page <= sourceEvidence.page_count; page++) {
      const outputPrefix = join(directory, "page");
      runCommand("pdftoppm", ["-f", String(page), "-l", String(page),
        "-singlefile", "-scale-to", "1800", "-png", input, outputPrefix],
        { timeoutMs: 25000, maxOutputBytes: 2 * 1024 * 1024 });
      const text = String(runCommand("tesseract", [outputPrefix + ".png", "stdout", "--psm", "6"],
        { timeoutMs: 25000, maxOutputBytes: 2 * 1024 * 1024 }) || "").trim();
      if (text.length > maxCharsPerPage)
        throw new DocumentIntakeError("document_ocr_text_limit");
      pages.push({ page_number: page, text, has_ocr_text: Boolean(text),
        verified: false });
    }
    return Object.freeze({ schema: "jason.document_intake.ocr.v1",
      source_sha256: sourceEvidence.source_sha256, pages,
      extraction_complete: pages.every(p => p.has_ocr_text),
      accounting_validated: false, rendered_verified: false });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

