"""Foreground localhost demo; internal synthetic capability lasts only for owned storage."""

import os
import socket
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import SecretStr

from pfa.analytics.fixtures import seed
from pfa.annotation import pilot_store as store
from pfa.api.app_factory import create_app
from pfa.db.session import Database, DbSettings, migrate
from pfa.release.config import load


def available(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        return False
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


@contextmanager
def application(project_root, settings, *, identifier_seed=None):
    rules = load(project_root)
    if (
        settings.mode != "DEMO_ONLY"
        or settings.environment == "production"
        or not settings.credentials
    ):
        raise ValueError("Explicit local DEMO_ONLY role credentials required")
    with TemporaryDirectory(prefix="pfa-release-demo-") as temporary:
        root = Path(temporary)
        (root / "configs").mkdir()
        for name in ("taxonomy_v1.yaml", "dataset_sources.yaml", "analytics_v1.yaml"):
            (root / "configs" / name).write_bytes((project_root / "configs" / name).read_bytes())
        store.private_directory(root / "data/private")
        with store.synthetic_session(root):
            database = Database(
                root,
                DbSettings(
                    mode="SYNTHETIC",
                    url=SecretStr("sqlite:///" + (root / "data/private/demo.sqlite").as_posix()),
                ),
            )
            try:
                migrate(database)  # Explicit creation of our own new disposable database only.
                fixtures = seed(
                    database,
                    identifier_seed=(
                        rules.fixture_seed if identifier_seed is None else identifier_seed
                    ),
                )
                app = create_app(
                    settings.model_copy(update={"environment": "test"}),
                    root=root,
                    database_factory=lambda: database,
                )
                yield app, database, root, fixtures
            finally:
                database.close()


def serve_api(root, port, identifier_seed=None):
    import uvicorn

    from pfa.api.settings import ApiSettings
    from pfa.release.preflight import preflight

    if preflight(root)["status"] == "BLOCKED" or not available(port):
        raise ValueError("Demo preflight or localhost port unavailable")
    settings = ApiSettings()
    with application(root, settings, identifier_seed=identifier_seed) as (app, _, _, _):
        uvicorn.run(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")


def serve_dashboard(root, port):
    from pfa.release.preflight import preflight

    if preflight(root)["status"] == "BLOCKED" or not available(port):
        raise ValueError("Demo preflight or localhost port unavailable")
    # Foreground child inherits protected process environment; no secret command arguments.
    environment = os.environ.copy()
    for name in (
        "PFA_API_PRINCIPALS",
        "PFA_API_KEY",
        "PFA_DB_URL",
        "TEST_DATABASE_URL",
        "PFA_FINGERPRINT_KEY",
    ):
        environment.pop(name, None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(root / "dashboard/app.py"),
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        cwd=root,
        env=environment,
        check=False,
    ).returncode
