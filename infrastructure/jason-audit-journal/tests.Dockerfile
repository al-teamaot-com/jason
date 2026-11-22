FROM python@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a
USER 0:0
RUN ln -s /usr/local/bin/python3 /usr/bin/python3 && groupadd -g 1000 al && useradd -u 1000 -g 1000 -M al
COPY --chown=0:0 implementation/orchestrator/event_store.py implementation/orchestrator/segmented_journal.py implementation/orchestrator/journal_sql.py implementation/orchestrator/journal_health.py implementation/orchestrator/journal_recovery.py implementation/orchestrator/journal_mount.py implementation/orchestrator/journal_outcomes.py /usr/local/lib/jason/audit-journal/trusted/implementation/orchestrator/
COPY --chown=0:0 tools/audit_journal_control.py tools/audit_journal_install_transaction.py tools/audit_journal_install.py tools/audit_journal_release_scope.py /usr/local/lib/jason/audit-journal/trusted/tools/
COPY --chown=0:0 tools/audit_journal_signed_owner_bridge.py /usr/local/lib/jason/audit-journal/trusted/tools/audit_journal_signed_owner_bridge.py
RUN chmod -R a-w /usr/local/lib/jason/audit-journal/trusted
COPY --chown=0:0 tools/tests/audit_journal_root_fixture.py /test.py
COPY --chown=0:0 tools/tests/audit_journal_bootstrap_fixture.py /bootstrap_fixture.py
COPY --chown=0:0 tools/tests/audit_journal_installer_fixture.py /installer_fixture.py
COPY --chown=0:0 tools/tests/audit_journal_signed_owner_root_fixture.py /signed-owner-fixture.py
COPY --chown=0:0 tools/audit_journal_owner_native_worker.py /test-source/worker.py
COPY --chown=0:0 tools/audit_journal_owner_executor_bootstrap.py /test-source/audit_journal_owner_executor_bootstrap.py
COPY --chown=0:0 tools/audit_journal_owner_native_worker.py /test-source/audit_journal_owner_native_worker.py
COPY --chown=0:0 infrastructure/jason-audit-journal-owner-executor/jason-audit-journal-owner-executor.service /test-source/jason-audit-journal-owner-executor.service
COPY --chown=0:0 infrastructure/jason-audit-journal-owner-executor/jason-audit-journal-owner-executor.path /test-source/jason-audit-journal-owner-executor.path
COPY --chown=0:0 tools/tests/audit_journal_owner_executor_root_bootstrap_fixture.py /root-bootstrap-fixture.py
COPY --chown=0:0 tools/tests/audit_journal_owner_native_worker_root_fixture.py /root-worker-fixture.py
ENTRYPOINT ["/usr/bin/python3","-I","-B","/test.py"]
