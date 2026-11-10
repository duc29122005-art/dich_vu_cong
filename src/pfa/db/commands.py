"""Safe CLI status and isolated tests; no reset, implicit migration or credential output."""

from pfa.db.session import Database, DbSettings


def run(root, action):
    if action == "smoke":
        from pfa.db.smoke import smoke

        return smoke(root), 0
    if action == "smoke-postgres":
        from pfa.db.postgres import smoke

        return smoke(root)
    try:
        settings = DbSettings()
        if settings.mode == "DISABLED":
            return {"status": "PERSISTENCE_DISABLED", "REAL_DATA_PERSISTENCE": "BLOCKED"}, 3
        database = Database(root, settings)
        try:
            database.validate()
        finally:
            database.close()
        return {
            "status": "SCHEMA_COMPATIBLE",
            "mode": settings.mode,
            "REAL_DATA_PERSISTENCE": "BLOCKED",
        }, 0
    except Exception:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Check protected configuration and explicit migrations",
        }, 4
