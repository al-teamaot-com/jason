FROM python@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a
USER 0:0
RUN ln -s /usr/local/bin/python3 /usr/bin/python3 && groupadd -g 1000 al && useradd -u 1000 -g 1000 -M al
COPY --chown=0:0 tools/audit_full_health_p0_recovery.py /test-source/tools/audit_full_health_p0_recovery.py
COPY --chown=0:0 tools/audit_full_health_p0_snapshot.py /test-source/tools/audit_full_health_p0_snapshot.py
COPY --chown=0:0 tools/audit_full_health_p0_operational.py /test-source/tools/audit_full_health_p0_operational.py
COPY --chown=0:0 tools/openclaw_authority_health_snapshot.py /test-source/tools/openclaw_authority_health_snapshot.py
COPY --chown=0:0 config/audit-full-health-p0-recovery.conf /test-source/config/audit-full-health-p0-recovery.conf
COPY --chown=0:0 tools/tests/audit_full_health_p0_root_fixture.py /test.py
RUN chmod -R a-w /test-source /test.py
ENTRYPOINT ["/usr/bin/python3","-I","-B","/test.py"]
