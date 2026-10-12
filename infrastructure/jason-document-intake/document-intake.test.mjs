import assert from "node:assert/strict";
import { test } from "node:test";
import { existsSync, statSync } from "node:fs";
import { ReadableStream } from "node:stream/web";
import {
  DocumentIntakeError,
  inspectPdfBuffer,
  readBoundedResponse,
  toProcurementDocument,
} from "./document-intake.mjs";

const raw = Buffer.from("%PDF-1.7\nsynthetic test data", "utf8");

function fakeTools({ pages = 2, text = "Invoice 10.00", imageList = "", encrypted = false } = {}) {
  const invocations = [];
  function run(program, args) {
    invocations.push({ program, args });
    const file = args.find(value => typeof value === "string" && value.endsWith("/source.pdf"));
    assert.ok(file && existsSync(file), "PDF source exists only for the duration of inspection");
    assert.equal(statSync(file).mode & 0o777, 0o600);
    switch (program) {
      case "pdfinfo":
        return "Pages: " + pages + "\nEncrypted: " + (encrypted ? "yes" : "no") + "\n";
      case "pdfimages":
        return "page num type width height color\n" + imageList;
      case "pdftotext":
        return text;
      default:
        throw Error("unapproved tool");
    }
  }
  return { run, invocations };
}

test("shared native-text extraction emits provenance and exact procurement adapter", () => {
  const tools = fakeTools();
  const doc = inspectPdfBuffer(raw, { runCommand: tools.run, pageInventory: true });
  assert.equal(doc.schema, "jason.document_intake.pdf.v1");
  assert.equal(doc.document_kind, "native_text");
  assert.equal(doc.page_count, 2);
  assert.equal(doc.pages.length, 2);
  assert.equal(doc.pages[0].native_text_present, null);
  assert.equal(doc.extracted_text, "Invoice 10.00");
  assert.equal(doc.rendered_verified, false);
  assert.equal(doc.accounting_validated, false);
  assert.equal(doc.source_sha256.length, 64);
  assert.deepEqual(toProcurementDocument(doc, { name: "invoice.pdf", sourceId: "teams-id" }), {
    name: "invoice.pdf",
    content_type: "application/pdf",
    size: raw.length,
    sha256: doc.source_sha256,
    extracted_text: doc.extracted_text,
    source_id: "teams-id",
  });
  assert.deepEqual(tools.invocations.map(item => item.program), [
    "pdfinfo", "pdfimages", "pdftotext",
  ]);
  assert.equal(existsSync(tools.invocations[0].args[0]), false, "temporary PDF removed");
});

test("shared hybrid detection counts imagery by page", () => {
  const tools = fakeTools({ imageList: "1  0 image 100 100 rgb\n2  1 image 100 100 rgb\n" });
  const result = inspectPdfBuffer(raw, { runCommand: tools.run, pageInventory: true });
  assert.equal(result.document_kind, "hybrid");
  assert.deepEqual(result.pages.map(p => p.image_count), [1, 1]);
});

test("image-only scans are identified without pretending they were extracted", () => {
  const tools = fakeTools({ text: "", imageList: "1  0 image 100 100 rgb\n" });
  const result = inspectPdfBuffer(raw, { runCommand: tools.run });
  assert.equal(result.document_kind, "scanned");
  assert.equal(result.has_native_text, false);
  assert.throws(
    () => toProcurementDocument(result, { name: "scan.pdf" }),
    error => error.code === "document_procurement_not_ready",
  );
  assert.throws(
    () => inspectPdfBuffer(raw, { runCommand: tools.run, requireNativeText: true }),
    error => error.code === "document_native_text_required",
  );
});

test("encrypted, invalid and oversized documents fail closed", () => {
  assert.throws(() => inspectPdfBuffer(Buffer.from("not a pdf")),
    error => error.code === "document_not_pdf");
  assert.throws(() => inspectPdfBuffer(raw, { maxBytes: 5 }),
    error => error.code === "document_size_limit");
  assert.throws(() => inspectPdfBuffer(raw, { runCommand: fakeTools({ encrypted: true }).run }),
    error => error.code === "document_encrypted");
  assert.throws(() => inspectPdfBuffer(raw, { maxPages: 1, runCommand: fakeTools().run }),
    error => error.code === "document_page_limit_or_invalid_count");
});

test("unreadable text/image evidence and truncated text fail closed", () => {
  assert.throws(() => inspectPdfBuffer(raw, { runCommand: fakeTools({ text: "" }).run }),
    error => error.code === "document_unreadable");
  assert.throws(() => inspectPdfBuffer(raw, { maxTextChars: 4, runCommand: fakeTools().run }),
    error => error.code === "document_text_limit");
});

test("PDF tool errors do not leak stderr or document text", () => {
  assert.throws(
    () => inspectPdfBuffer(raw, {
      runCommand: () => { throw new Error("Sensitive PDF content and path"); },
    }),
    error => error.code === "document_preflight_failed"
      && !error.message.includes("Sensitive"),
  );
});

test("legacy invoice output rejects unsupported/unbounded identifiers", () => {
  const doc = inspectPdfBuffer(raw, { runCommand: fakeTools().run });
  assert.throws(() => toProcurementDocument(doc, { name: "x.txt" }),
    error => error.code === "document_filename_invalid");
  assert.throws(() => toProcurementDocument(doc, { name: "x.pdf", sourceId: "a".repeat(257) }),
    error => error.code === "document_source_id_limit");
});

function responseFor(parts, length) {
  return {
    headers: { get: () => length === undefined ? null : String(length) },
    body: new ReadableStream({
      start(controller) {
        for (const bytes of parts) controller.enqueue(Uint8Array.from(bytes));
        controller.close();
      },
    }),
  };
}

test("shared response reader verifies declared and actual byte limits", async () => {
  const ok = await readBoundedResponse(responseFor([[1, 2], [3]]), 3);
  assert.deepEqual([...ok], [1, 2, 3]);
  await assert.rejects(() => readBoundedResponse(responseFor([[1]], 100), 3),
    error => error.code === "document_download_size_limit");
  await assert.rejects(() => readBoundedResponse(responseFor([[1, 2], [3, 4]]), 3),
    error => error.code === "document_download_size_limit");
  await assert.rejects(() => readBoundedResponse(responseFor([]), 3),
    error => error.code === "document_download_empty");
});


/** Real text-bearing one-page PDF created without third-party test libraries. */
function minimalNativeTextPdf() {
  const stream = "BT /F1 12 Tf 72 720 Td (Invoice 10.00) Tj ET\n";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Length " + Buffer.byteLength(stream) + " >>\nstream\n" + stream + "endstream",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  for (let i = 0; i < objects.length; i++) {
    offsets.push(Buffer.byteLength(pdf));
    pdf += (i + 1) + " 0 obj\n" + objects[i] + "\nendobj\n";
  }
  const xref = Buffer.byteLength(pdf);
  pdf += "xref\n0 " + (objects.length + 1) + "\n";
  pdf += "0000000000 65535 f \n";
  for (const offset of offsets.slice(1)) {
    pdf += String(offset).padStart(10, "0") + " 00000 n \n";
  }
  pdf += "trailer\n<< /Size " + (objects.length + 1) + " /Root 1 0 R >>\n";
  pdf += "startxref\n" + xref + "\n%%EOF\n";
  return Buffer.from(pdf, "utf8");
}

test("real Poppler PDF extraction and inventory smoke test", () => {
  const doc = inspectPdfBuffer(minimalNativeTextPdf(), { pageInventory: true });
  assert.equal(doc.page_count, 1);
  assert.equal(doc.document_kind, "native_text");
  assert.match(doc.extracted_text, /Invoice 10\.00/);
  assert.equal(doc.extraction_complete, true);
  assert.equal(doc.accounting_validated, false);
});
