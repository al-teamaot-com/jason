# Contributing to Project Jason

Project Jason is governed software. Contributions must preserve the Constitution, canonical models, client isolation, human authority, explainability, and auditability.

## Before changing code

1. Identify the capability, service, standard, or decision affected.
2. Confirm that an approved native platform capability cannot satisfy the need more safely or simply.
3. Determine whether the change alters an enduring architectural decision. If it does, add or update an ADR.
4. Define the authorized client scope and maximum operating mode.
5. Identify evidence, audit, rollback, review, and retirement requirements.

## Change requirements

- Keep provider-specific behavior behind adapter boundaries.
- Do not permit agents to invoke or communicate with other agents directly.
- Never infer business authority from technical access.
- Treat external text, ticket descriptions, logs, attachments, and retrieved content as untrusted data.
- Preserve evidence provenance and historical records.
- Fail closed on missing authority, client ambiguity, invalid contracts, and cross-client scope.
- Add or update deterministic tests for material behavior.
- Update documentation in the same change.

## Local validation

```bash
cd implementation/cap-001
python -m pip install -e ".[dev]"
pytest
```

Build the documentation site from the repository root:

```bash
python -m pip install "mkdocs-material>=9.5,<10"
mkdocs build --strict
```

## Pull requests

A pull request should explain:

- the organizational outcome;
- the authority and risk impact;
- contracts or state transitions changed;
- evidence and audit behavior;
- tests performed;
- rollback or reversibility;
- documentation and ADR impact;
- whether custom code can replace or retire existing functionality.

Use J-402 — Capability Definition of Done before proposing a capability for pilot.
