# Catalog write authorization: single-setting Owner maintenance

**Source only. No live application, deployment, or provider write has occurred.**

The production MCP still recognizes `person-al` as its only legacy Owner
administrator under `JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES`. The
regular, independently Entra-verified Owner principal
`person-entra-bee80bdcffb04c50b453c09d4d411f5f` is currently rejected by
`list_exact_authority_grants` with `AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`.
This one-time, exact-image helper adds that verified principal to the current
Owner *administration* allowlist while retaining `person-al`. The two other
Owner identities are not conflated. It does not itself issue any authority
grant, approve any catalog mutation, or deploy code.

- Source: `tools/owner_allowlist_same_image_20261117.py`
- Scope SHA256: `dc949f7dcf419cc22ea6f6bd3668597a199422d58a630a4c48c95a1979e65ad8`
- Reviewed helper SHA256: `609f715771519a1c0086aa08a5acbfcc145d1de35115f534ba2417f0f8c191f6`
- Pinned running source: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`
- Pinned MCP image: `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`
- Expected freeze SHA256: `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`
- Exactly one environment key changes; all other image, mounts, security,
  network, container configuration, and running runtime source must agree.

## Evidence

- `--review` returned `status=review_only`, `no_mutations=true`, exact source,
  image, original allowlist and freeze matched, on the live host.
- `tools/tests/test_owner_allowlist_same_image_20261117.py`: 10/10 offline tests
  passed for immutability checks, invalid changes, duplicate keys, unauthorized
  non-Owner invocation and the non-mutating review contract.
- No production change was executed. The helper deliberately refuses automated
  application: actual application requires an individual locally authenticated
  `al` Owner sudo session, interactive terminal, exact helper hash and an
  independently displayed scope-challenge answer. It cannot be executed by a
  remote orchestration tool or treated as ChatGPT approval.

After a permitted application, inspect the auditable transaction receipt,
re-read the unchanged production freeze, confirm that only the Owner allowlist
changed, then issue *only* the four specific catalog grants via Jason's native
Owner tool with `approval_required=true` for the authenticated human. This
maintenance does **not** alter provider execution identity. That separate
catalog release remains governed under PR #2515.

Do not turn an ordinary typed-chat instruction into evidence that the local
sudo exact-action challenge took place. Stop if any pinned source, image,
freeze, audit ownership or runtime health changes.
