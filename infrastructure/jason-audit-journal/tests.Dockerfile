FROM python@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a
USER 0:0
RUN ln -s /usr/local/bin/python3 /usr/bin/python3 && groupadd -g 1000 al && useradd -u 1000 -g 1000 -M al
COPY --chown=0:0 implementation/orchestrator/event_store.py implementation/orchestrator/segmented_journal.py implementation/orchestrator/journal_sql.py implementation/orchestrator/journal_health.py implementation/orchestrator/journal_recovery.py implementation/orchestrator/journal_mount.py implementation/orchestrator/journal_outcomes.py /usr/local/lib/jason/audit-journal/trusted/implementation/orchestrator/
COPY --chown=0:0 tools/audit_journal_control.py tools/audit_journal_install_transaction.py tools/audit_journal_install.py tools/audit_journal_release_scope.py /usr/local/lib/jason/audit-journal/trusted/tools/
RUN chmod -R a-w /usr/local/lib/jason/audit-journal/trusted
COPY --chown=0:0 tools/tests/audit_journal_root_fixture.py /test.py
COPY --chown=0:0 tools/tests/audit_journal_bootstrap_fixture.py /bootstrap_fixture.py
COPY --chown=0:0 tools/tests/audit_journal_installer_fixture.py /installer_fixture.py
ENTRYPOINT ["/usr/bin/python3","-I","-B","/test.py"]
