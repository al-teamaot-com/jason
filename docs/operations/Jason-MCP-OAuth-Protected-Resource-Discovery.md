# Jason MCP OAuth protected-resource discovery

The public Jason MCP protected-resource metadata endpoint is
`https://mcp-jason.teamaot.com/.well-known/oauth-protected-resource`.
It should return HTTP 200 with a JSON object naming the MCP resource,
the configured authorization server, and the Jason scope. The OAuth
issuer and token endpoint are separately advertised through the authorization
server metadata endpoint; changing issuer settings requires compatibility
verification with Microsoft Entra and the ChatGPT MCP connector.

Read-only acceptance: confirm the discovery response matches the configured
MCP resource URI, then run a client-side authorization and refresh lifecycle
test with redacted diagnostics. A successful discovery request alone does not
prove that reconnect prompts have been fixed. Roll out only through the
governed exact-revision release path; do not log authorization codes or tokens.
