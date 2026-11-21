FROM python@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a
USER 0:0
RUN ln -s /usr/local/bin/python3 /usr/bin/python3 && groupadd -g 1000 al && useradd -u 1000 -g 1000 -M al
COPY --chown=0:0 implementation/orchestrator/event_store.py implementation/orchestrator/segmented_journal.py implementation/orchestrator/journal_sql.py implementation/orchestrator/journal_health.py /usr/local/lib/jason/audit-journal/trusted/implementation/orchestrator/
COPY --chown=0:0 tools/audit_journal_control.py /usr/local/lib/jason/audit-journal/trusted/tools/
RUN chmod -R a-w /usr/local/lib/jason/audit-journal/trusted
COPY --chown=0:0 tools/tests/audit_journal_root_fixture.py /test.py
ENTRYPOINT ["/usr/bin/python3","-I","-B","/test.py"]
