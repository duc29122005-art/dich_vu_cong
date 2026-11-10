"""Explicit engines/sessions and migration checks; startup never performs DDL."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from pfa.annotation import pilot_store as store
from pfa.data.official_io import IngestionBlocked

HEAD = "0013_initial"


class DbSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PFA_DB_", env_file=None, extra="forbid", hide_input_in_errors=True
    )
    mode: Literal["DISABLED", "SYNTHETIC"] = "DISABLED"
    url: SecretStr | None = Field(default=None, repr=False)
    pool_size: int = Field(default=2, ge=1, le=10)
    max_overflow: int = Field(default=0, ge=0, le=10)
    pool_timeout: int = Field(default=5, ge=1, le=30)


class Database:
    def __init__(self, root: Path, settings: DbSettings, *, schema: str | None = None):
        self.root, self.settings = root, settings
        if settings.mode == "DISABLED" or settings.url is None:
            raise IngestionBlocked("Database persistence disabled or unconfigured")
        try:
            url = make_url(settings.url.get_secret_value())
            options = {}
            if url.drivername == "sqlite":
                store.require_synthetic(root)
                if not url.database or url.database == ":memory:":
                    raise ValueError("Disposable file-backed SQLite required")
                store.safe_path(Path(url.database), root / "data/private")
                options["connect_args"] = {"check_same_thread": False, "timeout": 5}
            elif url.drivername == "postgresql+psycopg":
                options["connect_args"] = {"connect_timeout": 5}
                if schema is not None:
                    import re

                    store.require_synthetic(root)
                    if not re.fullmatch(r"pfa_test_[0-9a-f]{32}", schema):
                        raise ValueError("Invalid isolated PostgreSQL schema")
                    options["connect_args"]["options"] = "-csearch_path=" + schema
            else:
                raise ValueError("PostgreSQL psycopg driver required")
            self.engine = create_engine(
                url,
                echo=False,
                hide_parameters=True,
                pool_pre_ping=True,
                pool_size=settings.pool_size,
                max_overflow=settings.max_overflow,
                pool_timeout=settings.pool_timeout,
                **options,
            )
            if url.drivername == "sqlite":

                @event.listens_for(self.engine, "connect")
                def sqlite_constraints(connection, record):
                    connection.execute("PRAGMA foreign_keys=ON")
                    connection.execute("PRAGMA busy_timeout=5000")

            self.sessions = sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        except Exception:
            raise IngestionBlocked("Database configuration invalid or unavailable") from None

    def validate(self):
        from pfa.db.models import Base

        with self.engine.connect() as connection:
            inspector = inspect(connection)
            if not inspector.has_table("alembic_version") or connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars().all() != [HEAD]:
                raise IngestionBlocked("Explicit Alembic migration required")
            for name, table in Base.metadata.tables.items():
                if not inspector.has_table(name) or {
                    c["name"] for c in inspector.get_columns(name)
                } != set(table.columns.keys()):
                    raise IngestionBlocked("Database schema incompatible")
            if connection.dialect.name == "sqlite":
                guards = set(
                    connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type='trigger'")
                    ).scalars()
                )
                expected = {
                    f"immutable_{table}_{action}"
                    for table in (
                        "prediction",
                        "review_event",
                        "source_registry",
                        "model_version",
                        "feedback",
                    )
                    for action in ("UPDATE", "DELETE")
                }
            else:
                guards = set(
                    connection.execute(
                        text(
                            "SELECT c.relname || ':' || t.tgname FROM pg_trigger t "
                            "JOIN pg_class c ON c.oid=t.tgrelid "
                            "JOIN pg_namespace n ON n.oid=c.relnamespace "
                            "WHERE n.nspname=current_schema() AND NOT t.tgisinternal"
                        )
                    ).scalars()
                )
                expected = {
                    table + ":immutable_history"
                    for table in ("prediction", "review_event", "source_registry", "model_version")
                } | {"feedback:immutable_feedback"}
            if not expected.issubset(guards):
                raise IngestionBlocked("Required database history guards missing")

    def close(self):
        self.engine.dispose()


def migrate(database: Database):
    """Internal synthetic helper only. Operators use explicit Alembic upgrade commands."""
    store.require_synthetic(database.root)
    from alembic import command
    from alembic.config import Config

    project = Path(__file__).resolve().parents[3]
    config = Config(str(project / "alembic.ini"))
    config.set_main_option("script_location", str(project / "migrations"))
    with database.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    database.validate()
