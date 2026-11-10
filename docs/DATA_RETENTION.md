# Retention, deletion, restricted access and backups

Real persistence remains BLOCKED. No approved real records, privacy clearance or
retention evidence exists. This document is an operational requirement, not a human
approval or a license. Naming a column `text_redacted` is not anonymization.

Current API intake accepts only bundled invented fixture IDs. Privacy screening
rejects suspected sensitive fixture content before any database write. Arbitrary
submitted feedback is rejected; transient prediction inputs are never saved. Even
screened synthetic text requires an explicit text-access grant. Metadata defaults
exclude text, and only ADMIN can read audit history. Synthetic flags and source
references cannot be changed to make records research gold.

Offline smoke files live in a restricted temporary directory and are removed after
sessions/engine close, including failed checks. Local PostgreSQL synthetic records
persist until the operator follows a reviewed retention procedure. No unapproved
retention duration is invented. Before keeping any real records, the owner must
approve purpose, permitted fields/scopes, exact retention period, legal hold handling,
data subjects' request route, responsible operator, deletion deadlines and backup
expiry. Bind that evidence through existing source/permission and STEP 04 privacy
review; a future real intake adapter must enforce it.

There is no API deletion or reset endpoint. Append-only guards deliberately block
record/history deletion. Approved erasure therefore requires an offline privileged
maintenance procedure: verify authorization and retention obligations, pause writers,
identify affected opaque references, back up only if retention permits, execute a
reviewed migration/redaction or storage retirement plan, verify all replicas/exports,
record non-sensitive deletion metadata separately, and document backup expiry.
Do not disable triggers casually or claim secure erasure from normal file removal.
No automated erasure, encryption-at-rest or cryptographic deletion is implemented.

Backups require access restrictions at least as strong as the source database,
separate credentials, approved encryption/transport controls, inventory, retention
expiry and periodic restore checks. PostgreSQL data volumes, WAL, snapshots, dumps,
host crash dumps and replicas can retain content after a primary record is removed.
Use PostgreSQL-supported backup tooling under an approved policy; never commit dumps
or credentials. Test restores in an isolated authorized database before migrations.

The runtime DB role should have only required table SELECT/INSERT and restricted
feedback UPDATE permissions, no ownership, DDL, TRUNCATE, trigger changes or broad
server rights. Protect PostgreSQL installation, loopback access and host accounts.
Database URLs stay in protected process environment settings, SQL echo is off, and
errors/logs omit text and credentials. Reverse-proxy/SQL debug logging requires its
own review. Git ignores data, SQLite files and model artifacts; operators must keep
PostgreSQL volumes and dumps outside tracked paths as well.
