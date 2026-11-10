# Backup, restore and migration safety

These are operator instructions, not automatic production operations. No STEP 16 command
backs up citizen data, resets a database, rotates credentials or restores a production DB.
Keep demo, test and future authorized research stores separate. Restrict backups to the
authorized operator, encrypt storage and transport, and apply the source-specific retention
and withdrawal policy. Never put backups, database URLs or participant mappings in Git.

## PostgreSQL on Windows

Existing installation is `D:\PostgreSQL\18`; Docker/reinstallation is unnecessary.
Use an approved PostgreSQL service definition and protected password file/environment;
never put passwords in shell command arguments or shared transcripts. The following uses
operator-defined `pfa_authorized_local` and an explicitly named **new** recovery database:

```powershell
& 'D:\PostgreSQL\18\bin\pg_dump.exe' --dbname='service=pfa_authorized_local' --format=custom --file='D:\protected-backups\pfa-reviewed.dump'
& 'D:\PostgreSQL\18\bin\pg_restore.exe' --list 'D:\protected-backups\pfa-reviewed.dump'
# Create a NEW isolated recovery database through the approved operator procedure first.
& 'D:\PostgreSQL\18\bin\pg_restore.exe' --dbname='service=pfa_new_recovery' --single-transaction --exit-on-error 'D:\protected-backups\pfa-reviewed.dump'
```

Confirm target names, ownership, free space, backup integrity, encryption and restore
authorization before execution. Do not use `--clean`, `--create` or a production target
without a separate reviewed recovery plan. Test restore on isolated infrastructure and
compare schema revision, constraints, triggers, row counts and source permission state.
A backup that has not been restored successfully is not proven recoverable.

## Migrations

Read [DATABASE_MIGRATIONS.md](DATABASE_MIGRATIONS.md). Inspect Alembic history/current
revision and the proposed SQL before upgrading. Current expected head is `0013_initial`.
The API startup validates schema compatibility but never runs DDL. Before a future
production migration: back up, rehearse restore and upgrade in a clone, restrict writes,
review irreversible operations, and record the change. Use Alembic CLI with the existing
environment-only DB configuration. STEP 16 adds no destructive migration.

On failure, stop writes and inspect transaction/schema state privately. Prefer a reviewed
forward repair or restore into a new database followed by an authorized switch. Never
assume downgrade is lossless or blindly rerun destructive scripts. Test smokes delete
only their newly owned UUID-named test schema, never another user's schema/database.
Inspect orphaned `pfa_test_<uuidhex>` schemas after a reported cleanup failure; do not
automatically remove schemas based on a name prefix alone.

## Model and retention recovery

Use existing registry inspection and artifact hash verification before serving. Registry
rollback follows STEP 11 lifecycle/approval checks; demo rollback never creates research
approval. Preserve append-only registry and review history. A DB model reference is not
an independent approval authority. Restore source/consent revocations as well as data;
an older backup must not resurrect expired permissions.

Secure deletion on SSDs, snapshots and backups is not guaranteed by deleting a file.
Use encryption/key lifecycle, documented retention and verified backup expiration.
Legal/provider retention requirements and participant withdrawal govern future research
storage. No real-data retention authorization currently exists.
