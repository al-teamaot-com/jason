# PMv4 Stage A0 source release — separate M365 group-admin activation

**State:** SOURCE-ONLY PREPRODUCTION REVIEW. **Never authorizes production deployment.**

## Why this boundary is required

Protected main at `6bfdb76bd3e0bbbb11e09b3c213deaec04f1771a` built the official native release `release-6bfdb76bd3e0bbbb`, including the PMv4 Stage A0 Owner issuer **and** a separately governed Microsoft 365 AOT group-admin pilot. The native root preproduction environment successfully isolated its runtime container, but both native runtime and MCP `--preflight` checks returned `DENIED: Microsoft group AppRole runtime projection unavailable or unsafe`.

The existing production staging documents say the four protected role-ID and secret-ID files require a separate, root-authorized permission repair to become `root:1000 0640`. Those files cannot be checked conclusively by the unprivileged release process and are **not proven safe for mounting**. The PMv4 release is not authority to perform that unrelated root change or activate Microsoft Graph group writes.

## Exact source-only separation

- Set `config/microsoft_graph/group-admin-release.json` to the literal minimal `{"schema_version":"1.0","service":"aot-microsoft-group-admin","profile":"off"}`; omit all active tenant/client fields.
- The existing fail-closed `tools/microsoft_group_admin_release_profile.py` now recognizes **only** this exact OFF declaration or the existing exact AOT ON declaration. OFF yields the empty string.
- Both existing native production deploy scripts already guard their four group AppRole binds behind nonempty source activation. As a result, an OFF release requests **zero** new Microsoft group credential mounts, leaves `JASON_M365_GROUP_ADMIN_PROFILE=`, and retains all other existing provider mounts and container hardening.
- The independent M365 pilot ON declaration remains available as the reviewed `ALLOWED` schema. Re-enabling it requires a **future separate protected source change**, verified production AppRole permissions, native preflight, exact Owner approval and the independent Graph create/member-action approvals. This PR does **not** remove its code, Entra grants, authorization tests, previous root staging, or planned capabilities.
- The PMv4 Stage A0 Owner issuer ON profile remains exactly as previously source-promoted. This change does not activate the issuer, run Stage A0 installation, change ticket processing, freeze/hold, or restart runtime/MCP.

## Validation and governance

The revised source/profile and rollback tests must pass, including malformed OFF declarations, unauthorized client/tenant injection, unchanged exact ON schema, and no-secret-bind preflight. GitHub required checks must pass on the exact final candidate SHA. A separate exact Owner **source-only promotion** approval is required before merging; after merge all native candidate images, canonical 65-file-plus revised release scope and rollback evidence must be regenerated and reviewed from the then-current protected main. **No production action is authorized by source promotion.**

Native release `release-6bfdb76bd3e0bbbb` remains only `release_candidate` with Owner approval FALSE and preproduction FALSE, since its candidate source was not safe for the current credential mounts. Do not claim it production eligible.

This change is an isolation decision, not a workaround or false PASS: the old unsafe ON candidate will continue to fail its native preflight. Only a subsequent **fully rebuilt OFF candidate at a new protected-main SHA** can qualify. The native release manager's source/rollback controls remain unchanged.
