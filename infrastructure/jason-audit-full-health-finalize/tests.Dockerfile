FROM python@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a
USER 0:0
RUN ln -s /usr/local/bin/python3 /usr/bin/python3
COPY --chown=0:0 tools/audit_full_health_p0_recovery.py /test-source/tools/audit_full_health_p0_recovery.py
COPY --chown=0:0 tools/audit_full_health_p0_finalize.py /test-source/tools/audit_full_health_p0_finalize.py
COPY --chown=0:0 tools/tests/audit_full_health_p0_finalize_root_fixture.py /test.py
RUN chmod -R a-w /test-source /test.py
ENTRYPOINT ["/usr/bin/python3","-I","-B","/test.py"]
