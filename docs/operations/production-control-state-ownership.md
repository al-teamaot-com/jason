# Production control-state ownership

The root-run production drift watchdog must preserve the owner and group of the release-manager state directory when it atomically replaces `production-control-state.json`; its file mode remains `0600`. This allows the unprivileged release manager to read the circuit-breaker state without granting world access or weakening the breaker.

Pre-existing root-owned control-state files need a separately authorized one-time host repair; deploying the source change alone does not alter an existing file.
