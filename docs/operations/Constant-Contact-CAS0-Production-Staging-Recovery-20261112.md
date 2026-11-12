# Constant Contact production OpenBao staging — create-only CAS recovery

2026-11-12 • Source-only correction, no production modification.

## Incident and verified state

The Owner ran `sudo python3 /opt/jason/current/tools/provider_secret_provision.py constant_contact` after the governed release `d1b8c196dadd4b672ec8ba47075f27bb61c98d63` deployed. The command collected the Client ID, Client Secret and OAuth token-encryption key, then ended with `[PASS] Temporary administrative token revoked.` and `DENIED: OpenBao provisioning request failed with HTTP 400.`

Independent read-only investigation on the host confirmed:

- OpenBao health HTTP 200; the source production runtime and MCP are healthy and their freeze remains untouched.
- The dedicated root-owned AppRole credential directory exists, with `role-id`, `secret-id` and metadata files mode 0640, under a directory mode 0750.
- An isolated AppRole login to OpenBao succeeded (HTTP 200), proving the issued AppRole is usable.
- GET for the exact `secret/data/connectors/constant-contact/production/oauth-client` record returned **HTTP 404**. No OAuth client credential is stored at that path.
- GET `secret/config` using that read-only AppRole returned HTTP 403 by design; current live mount `cas_required` could not be read with this least-privilege token.
- A prior independently documented AOT incident in `docs/operations/Jason-Datto-RMM-Execution-Credential-Staging-2026-09-15.md` confirmed this shared KV-v2 mount has `cas_required=true`, and identical initial HTTP 400 failures occurred when the provisioning payload omitted CAS.
- Existing source attempted `POST /v1/secret/data/.../oauth-client` with `{"data": {...}}` and **no** `options.cas` field, after successfully configuring the AppRole and collecting the secret values. The root cause is therefore strongly supported, although the current admin-only mount configuration and sanitized OpenBao HTTP error body were not available to this read-only investigation.

## Corrections

1. For **Constant Contact only**, construct the KV-v2 payload with `options: {"cas": 0}`. This is **create-only**: if the record already exists, OpenBao must refuse overwriting any OAuth Client Secret or data-encryption key. Other provider provisioning payloads are unchanged.
2. Fail closed before any POST unless the `token_key_b64` field decodes as exactly 32 bytes. A blank secure key prompt now generates a fresh 256-bit AES-GCM key in memory using `os.urandom(32)`; it is not printed or written to a local file. A supplied key remains supported.
3. Correct the Owner-local OAuth CLI to use the **actual** root provisioner filenames `role-id` and `secret-id` rather than nonexistent `role_id` and `secret_id`. Do not introduce alternate credential trees.
4. Preserve all original root-only OpenBao admin sign-in, temporary token revocation, provider-scoped policy/AppRole, encrypted token store and required callback security checks. No direct Docker, provider POST, OAuth connection or production freeze change is performed by this source PR.

## Verification

Focused regression command:

```bash
PYTHONPATH=implementation python3 -m pytest -q \
  tools/tests/test_constant_contact_secret_provision.py \
  tools/tests/test_provider_secret_provision.py \
  implementation/connectors/tests/test_constant_contact_oauth.py \
  implementation/connectors/tests/test_constant_contact_oauth_store.py
```

Verifies CAS=0 exact protected path/payload, no alternate writes, no overwriting existing record (simulated KV CAS conflict), empty-key secure generation, malformed/short-key fail-closed before network call, unchanged non-Constant-Contact provider writes, root-generated AppRole filenames and incumbent OAuth contracts.

## Native release and live acceptance boundary

Merge source only after independent GitHub security/CI checks. An updated native production candidate requires exact protected-main SHA, full manual scope-review fingerprint, independent root LKG/rollback, breaker/freeze/health and signed authenticated Owner approval. Do not use an ad-hoc replacement `/opt/jason/current` script or direct OpenBao write to bypass this process.

When the *revised* provisioner is deployed and approved, the Owner must re-enter their saved Client Secret **locally**, since the initial attempted values were correctly not persisted. The existing AppRole files may be reused and must not be blindly rotated/deleted. Provisioning should return `status: pass`, then a fresh read-only AppRole GET must observe the new secret version without printing secret fields. Only then bind the protected AppRole paths into the runtime/MCP via a separately reviewed root deployment, complete OAuth with the registered HTTPS callback and owner-verified AOT account/list, execute one small consent-backed contact import and independent readback, then govern the GET-only timer activation after provider acceptance.

No external contacts or subscriptions were changed during this recovery effort.
