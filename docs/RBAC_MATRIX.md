# Local RBAC and source access

Roles are configured in protected `PFA_API_PRINCIPALS`, a JSON array. Each credential
has a unique stable pseudonymous `actor_id`, `role`, `source_ids`, `can_view_text`,
`can_adjudicate`, and high-entropy `key`. Credentials must be 32–256 printable ASCII
characters. Use unique generated credentials, not names/emails/password examples.
The configuration is environment-only and never appears in public status or logs.
Remove/rotate credentials and restart to revoke access; no role mutation API exists.
Review configuration changes through a protected operator change log outside Git.

Non-secret principal fields for a synthetic reviewer:

```json
{"actor_id":"synthetic_reviewer","role":"REVIEWER","source_ids":["synthetic_demo"],"can_view_text":true,"can_adjudicate":false}
```

Add a generated `key` only in protected configuration. This example alone is not a
usable credential. `PFA_API_KEY` remains valid for STEP 12 inference but grants no
persistence role. Client-provided roles, actor IDs and forwarded headers are ignored
as authority. Body role fields are rejected. All database routes authenticate before
reading request content. Missing configured auth fails closed with 503; wrong/missing
key returns 401; authenticated legacy key without a principal returns 403.

| Operation | ADMIN | REVIEWER | ANALYST |
|---|---|---|---|
| Create synthetic fixture | Yes | No | No |
| Read permitted metadata | Yes | Yes | Yes |
| Read synthetic aggregate analytics | Source-scoped | Source-scoped | Source-scoped |
| Read screened text | Explicit grant | Explicit grant | Explicit grant |
| Read review queue | Yes | Yes | No |
| Claim / confirm / correct / escalate | No | Assigned workflow | No |
| Assign review | Yes, configured eligible reviewer | No | No |
| Adjudicate | No | Explicit adjudication grant | No |
| Read audit history | Yes | No | No |
| Update/delete history | No | No | No |
| Approve model / elevate synthetic data | No | No | No |

Every role remains limited to `source_ids` and current source governance. ADMIN never
grants itself training, publication, real-data intake or model promotion rights. The
database source/model tables only snapshot references from existing authorities.
Only REVIEWER may receive `can_adjudicate=true`. Configuration grants software
capability, not proof that a distinct independent human performed an action.

Current deployment is local and demo only. Production needs reviewed identity
provisioning, credential revocation/rotation, TLS, rate limits, least-privilege DB
roles, host/backup controls and source-specific authorization review. API credentials
do not establish those controls. Keep CORS explicit and never expose the demo publicly.
