from datetime import datetime, timedelta, timezone
import unittest

from orchestrator.approval_audit import (
    ApprovalAuditEvent, ApprovalAuditEventType, ApprovalAuditRecorder,
    InMemoryApprovalAuditSink,
)
from orchestrator.approval_execution_trace import TraceQuery, read_trace

T = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)

def event(approval, org, corr, event_type, offset=0, metadata=None):
    return ApprovalAuditEvent(
        event_id=f"{approval}-{offset}", event_type=event_type,
        occurred_at=T + timedelta(minutes=offset), approval_id=approval,
        request_id=f"request-{approval}", correlation_id=corr, organization_id=org,
        client_id=None, actor_identity_id="private-person-id",
        capability="service.quote.create", metadata=metadata or {},
    )

class ApprovalExecutionTraceTests(unittest.TestCase):
    def query(self, **kw):
        return TraceQuery(organization_id="aot", start=T - timedelta(minutes=1),
                          end=T + timedelta(hours=1), correlation_id="arnold-1", **kw)

    def test_arnold_invoice_one_no_false_delivery(self):
        sink = InMemoryApprovalAuditSink()
        recorder = ApprovalAuditRecorder(sink)
        recorder.record(event("approval-1", "aot", "arnold-1", ApprovalAuditEventType.REQUEST_CREATED))
        recorder.record(event("approval-1", "aot", "arnold-1", ApprovalAuditEventType.DELIVERY_RECORDED, 1,
                              {"secret_token": "do-not-expose"}))
        result = read_trace(self.query(), sink.events, authorized_organization="aot",
                            audit_access_check=lambda _: True)
        self.assertEqual([r["state"] for r in result["events"]],
                         ["request_created", "transport_receipt_recorded"])
        self.assertFalse(result["delivery_confirmed"])
        self.assertNotIn("do-not-expose", str(result))
        self.assertNotIn("private-person-id", str(result))
        self.assertEqual(result["events"][1]["previous_event_hash"], sink.events[0].event_hash)

    def test_second_invoice_independent(self):
        events = [event("approval-1", "aot", "arnold-1", ApprovalAuditEventType.REQUEST_CREATED),
                  event("approval-2", "aot", "arnold-2", ApprovalAuditEventType.PROCESSING_FAILED, 2)]
        result = read_trace(self.query(), events, authorized_organization="aot",
                            audit_access_check=lambda _: True)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["approval_id"], "approval-1")

    def test_second_user_isolated_by_exact_correlation(self):
        events = [event("approval-1", "aot", "arnold-1", ApprovalAuditEventType.REQUEST_CREATED),
                  event("approval-adam", "aot", "adam-1", ApprovalAuditEventType.REQUEST_CREATED)]
        self.assertEqual(len(read_trace(self.query(), events, authorized_organization="aot",
                          audit_access_check=lambda _: True)["events"]), 1)

    def test_cross_tenant_and_permission_fail_closed(self):
        events = [event("foreign", "other", "arnold-1", ApprovalAuditEventType.REQUEST_CREATED)]
        self.assertEqual(read_trace(self.query(), events, authorized_organization="aot",
                         audit_access_check=lambda _: True)["events"], [])
        with self.assertRaises(PermissionError):
            read_trace(self.query(), events, authorized_organization="other",
                       audit_access_check=lambda _: True)
        with self.assertRaises(PermissionError):
            read_trace(self.query(), events, authorized_organization="aot",
                       audit_access_check=lambda _: False)

    def test_bounded_query_and_no_wildcard(self):
        with self.assertRaises(ValueError):
            TraceQuery("aot", T - timedelta(days=8), T, correlation_id="arnold-1").validate()
        with self.assertRaises(ValueError):
            TraceQuery("aot", T, T + timedelta(minutes=1), correlation_id="*").validate()
        with self.assertRaises(ValueError):
            TraceQuery("aot", T, T + timedelta(minutes=1), correlation_id="arnold-1", limit=101).validate()

    def test_transport_failure_and_duplicate_event_prevention(self):
        sink = InMemoryApprovalAuditSink()
        recorder = ApprovalAuditRecorder(sink)
        e = event("approval-1", "aot", "arnold-1", ApprovalAuditEventType.PROCESSING_FAILED)
        recorder.record(e)
        with self.assertRaises(ValueError):
            recorder.record(e)
        result = read_trace(self.query(), sink.events, authorized_organization="aot",
                            audit_access_check=lambda _: True)
        self.assertEqual(result["events"][0]["state"], "failed")
        self.assertFalse(result["delivery_confirmed"])

if __name__ == "__main__":
    unittest.main()
