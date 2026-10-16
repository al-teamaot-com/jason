import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { extractScannedPdfPages } from "./ocr-fallback.mjs";

const bytes = Buffer.from("%PDF-test-document");
const evidence = { schema: "jason.document_intake.pdf.v1", size_bytes: bytes.length,
  source_sha256: createHash("sha256").update(bytes).digest("hex"), page_count: 2 };

test("bounded scanned OCR retains page provenance but never certifies amounts", () => {
  const calls = [];
  const result = extractScannedPdfPages(bytes, { sourceEvidence: evidence,
    runCommand(program, args) {
      calls.push(program);
      return program === "tesseract" ? "Invoice 15904 $826.91" : "";
    },
  });
  assert.deepEqual(calls, ["pdftoppm", "tesseract", "pdftoppm", "tesseract"]);
  assert.equal(result.pages[1].page_number, 2);
  assert.equal(result.accounting_validated, false);
  assert.equal(result.rendered_verified, false);
  assert.equal(result.extraction_complete, true);
});
test("wrong source hash fails closed before OCR", () => {
  assert.throws(() => extractScannedPdfPages(bytes,
    { sourceEvidence: { ...evidence, source_sha256: "0".repeat(64) } }),
    { code: "document_ocr_source_mismatch" });
});
test("unavailable OCR fails closed", () => {
  assert.throws(() => extractScannedPdfPages(bytes, { sourceEvidence: evidence,
    runCommand() { throw new Error("tool missing"); } }));
});
test("OCR with missing page text is incomplete", () => {
  const result = extractScannedPdfPages(bytes, { sourceEvidence: evidence,
    runCommand() { return ""; } });
  assert.equal(result.extraction_complete, false);
  assert.equal(result.pages.length, 2);
});
test("limits reject unbounded pages and extraction", () => {
  assert.throws(() => extractScannedPdfPages(bytes,
    { sourceEvidence: evidence, maxPages: 1 }), { code: "document_ocr_invalid_evidence" });
  assert.throws(() => extractScannedPdfPages(bytes,
    { sourceEvidence: evidence, maxCharsPerPage: 50001 }), { code: "document_ocr_limits" });
});
