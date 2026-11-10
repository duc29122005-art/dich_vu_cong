"""No URL in config/logs. Migrations are explicit operator actions, never API startup."""

from alembic import context

from pfa.core.config import Settings
from pfa.db.models import Base, UTCDateTime
from pfa.db.session import Database, DbSettings

config = context.config


def render_item(kind, value, autogen_context):
    if kind == "type" and isinstance(value, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline DDL generation is disabled; use a dedicated development DB")
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    database = Database(Settings().project_root, DbSettings())
    try:
        with database.engine.connect() as connection:
            run(connection)
    finally:
        database.close()
