from jason_connectors.artifact_evidence import (
    ArtifactAdmissionError,
    ArtifactDescriptor,
    ArtifactKind,
    Sensitivity,
    admit_artifact,
)


def descriptor(**overrides):
    values = dict(
        organization_id="org-100",
        kind=ArtifactKind.EVIDENCE,
        media_type="application/json",
        sensitivity=Sensitivity.CLIENT_CONFIDENTIAL,
        source_capability="cap-001.autotask",
        source_operation="ticket.query",
        correlation_id="corr-123",
        metadata={"purpose": "validation"},
    )
    values.update(overrides)
    return ArtifactDescriptor(**values)


def test_admission_returns_reference_without_embedding_content():
    ref = admit_artifact(
        descriptor(),
        b'{"status":"ok"}',
        storage_provider="jason-evidence-store",
        storage_locator="org-100/evidence/example.json",
        active_organization_id="org-100",
    )
    assert ref.organization_id == "org-100"
    assert ref.size_bytes == 15
    assert len(ref.content_sha256) == 64
    assert not hasattr(ref, "content")


def test_cross_organization_artifact_is_denied():
    try:
        admit_artifact(
            descriptor(),
            b"evidence",
            storage_provider="store",
            storage_locator="org-100/evidence/x",
            active_organization_id="org-200",
        )
    except ArtifactAdmissionError as exc:
        assert "organization" in str(exc).lower()
    else:
        raise AssertionError("cross-organization artifact should be denied")


def test_empty_artifact_is_denied():
    try:
        admit_artifact(
            descriptor(),
            b"",
            storage_provider="store",
            storage_locator="org-100/evidence/x",
            active_organization_id="org-100",
        )
    except ArtifactAdmissionError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("empty artifact should be denied")


def test_missing_source_context_is_denied():
    try:
        admit_artifact(
            descriptor(source_capability=""),
            b"evidence",
            storage_provider="store",
            storage_locator="org-100/evidence/x",
            active_organization_id="org-100",
        )
    except ValueError as exc:
        assert "source_capability" in str(exc)
    else:
        raise AssertionError("missing source context should be denied")
