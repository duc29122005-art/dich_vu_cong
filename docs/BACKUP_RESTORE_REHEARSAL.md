# Explicit disposable PostgreSQL restore rehearsal

Status: **NOT_VERIFIED until actually executed**. This procedure is optional and never
runs from release smoke, preflight, API startup or CI. It does not use real research data
or overwrite pfa_test. Historical schema/concurrency verification does not prove restore.

1. Through approved PostgreSQL administration, explicitly create two NEW disposable local
   databases with unique names, for example a source ending `_demo_backup_test` and a
   distinct empty target ending `_demo_restore_test`. Verify neither name is pfa_test or
   an existing user/research DB. Record exact names and ownership privately. Restrict the login.
2. Configure protected PostgreSQL service definitions for those two exact databases, using
   password-file/environment protection. Never paste passwords into commands or transcripts.
3. Explicitly migrate ONLY the named empty source using the existing Alembic workflow and
   seed the existing synthetic analytics fixture. Record schema revision 0013_initial,
   420 feedback, 1,260 predictions, 1,050 simulated events and all-source SYNTHETIC flags.
   The existing seed function rejects nonempty tables; do not change that guard.
4. Stop writes, then use `D:\PostgreSQL\18\bin\pg_dump.exe --format=custom` for that source,
   writing to a protected path outside Git. Compute SHA256 with `Get-FileHash` and inspect
   the archive with `pg_restore.exe --list`. Record file size and checksum without credentials.
5. **Human confirmation required before restore:** inspect the target's actual database
   name, owner, emptiness and disposable status. Obtain explicit confirmation naming the
   target. Do not proceed from an inferred approval or elapsed time. No automatic command
   in this repository performs that confirmation or overwrites an existing database.
6. Restore into the explicitly created EMPTY target with `--single-transaction
   --exit-on-error`. Do not use `--clean`, `--create`, database reset or DROP DATABASE.
7. Verify target schema/Alembic revision, foreign keys, immutable-history triggers, exact
   known counts, taxonomy/provenance, synthetic flags and reopened-connection persistence.
   Recompute backup SHA256 and compare. Record the actual PostgreSQL/client versions.
8. Keep the backup restricted under the documented retention policy. Deletion of either
   database or dump is a separate destructive action: verify exact owned disposable names
   and ask for explicit human confirmation. Never remove other targets by prefix matching.

Use BACKUP_RESTORE.md and DATABASE_MIGRATIONS.md for command syntax and failure recovery.
Before reporting VERIFIED, retain an actual execution record with both exact target
identities in protected storage, checksum, restore exit code, count/constraint comparisons,
cleanup decision and operator confirmation. A template or successful SQLite smoke is not
such evidence. No rehearsal was authorized against a configured target in this release run.
