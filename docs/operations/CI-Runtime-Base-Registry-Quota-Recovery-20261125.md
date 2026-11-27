# Runtime CI base-image registry quota diagnostic

On November 25, the Teams shared-workflow PR #2700's clean runtime image build
failed at the existing ECR Public Python base-image pull. GitHub Actions job
139489203925 reported the exact terminal diagnostic
`Error response from daemon: error from registry: Data limit exceeded`.
The existing CI-only helper recognized HTTP 429 and Too Many Requests, but not
this bare registry diagnostic. Its existing test combined the text with HTTP
429, so it did not exercise the observed failure.

Recognize the exact bare diagnostic as eligible for the already-approved,
single fallback from the existing ECR Public mirror to the original Docker
Official Image. Do not rotate on ambiguous quota text, authorization/certificate
errors or unknown manifests, including mixed failure diagnostics. Continue
requiring one unambiguous content digest and one real successful build.
Do not retry application build failures or change the runtime Dockerfile,
production image selection, credentials, native release scope or approvals.

This change is source-only CI reliability work. Local mock transport tests do not
prove the external registries will be available. A real clean-checkout build
must pass before claiming live CI recovery.
