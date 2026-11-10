# Append-only review history

CREATE, CLAIM, ASSIGN, CONFIRM, CORRECT, ESCALATE, ADJUDICATE and relevant CONFLICT
events have stable UUIDs and globally unique operation IDs. Events contain only
pseudonymous actor/role, opaque feedback/prediction references, closed action/reason
codes, prior/proposed label IDs, versions and UTC timestamps. They contain no input
text, personal names, emails, free-form justifications, database URLs or credentials.
Assignment is an administrative action and records the designated actor. Role
configuration changes occur outside the API and need a separate protected operator
log; this implementation does not claim to audit external environment administration.

Successful events and current review state commit together. An audit-write failure
rolls back the state update. SQL compare-and-swap checks version and previous state;
two simultaneous reviewers cannot silently overwrite each other. A stale request
commits a CONFLICT event before returning 409 when the transaction remains available.
A database lock/connection failure may prevent a conflict audit; retry only after
reading current state. Duplicate operation IDs are rejected without duplicating the
original event. No retry changes history or model predictions.

History sorts by UTC event time, then successful review version for tied clock
values, then UUID; null-version conflicts follow successful events within that
same tick. Multiple tied conflict events have deterministic UUID order, not a
claimed causal order. Stored timestamps and immutable events are never rewritten.

SQLAlchemy guards reject ORM changes/deletion of prediction, source/model snapshots
and review events. Initial migration installs backend-specific UPDATE/DELETE triggers
for these tables and a feedback guard requiring immutable provenance and a version
increment. Application startup requires these guards. There are no API mutations of
history. Direct SQL tests verify the database guards; SQLite tests alone do not
validate PostgreSQL trigger behavior.

These mechanisms protect against accidental/API writes. They are not cryptographic
tamper evidence, immutable storage, or protection against a privileged database
administrator. An owner can disable triggers, use TRUNCATE, rewrite files or restore
another backup. Runtime credentials must not own tables or have DDL/TRUNCATE rights.
Use reviewed privilege separation and protected external audit backups before any
real deployment. No additional independent model approval authority is created.

Audit history reads are ADMIN-only, source-scoped and paginated. Metadata is still
restricted research material. Synthetic adjudication explicitly records
`independent_human_validation=false`; no agreement or gold label is inferred. The
current solo researcher must not represent synthetic identities as human reviewers.
