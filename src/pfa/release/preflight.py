"""Read-only demo eligibility checks. Optional research/operations evidence stays separate."""

import importlib
import importlib.metadata as metadata
import importlib.util
import os
import re
import sys
import tomllib

import yaml
from packaging.requirements import Requirement

from pfa.api.identity import resolve
from pfa.api.settings import ApiSettings
from pfa.core.config import Settings
from pfa.data.registry import load_registry
from pfa.integration.security_checks import scan
from pfa.release.config import load


def locked(root):
    result = {}
    for line in (root / "requirements-ci.lock").read_text("utf-8").splitlines():
        if not line.strip() or line.startswith(("#", "--")):
            continue
        requirement = Requirement(line)
        specs = list(requirement.specifier)
        if requirement.url or len(specs) != 1 or specs[0].operator != "==":
            raise ValueError("Exact public dependency pins required")
        result[requirement.name] = specs[0].version
    if not result:
        raise ValueError("Empty dependency lock")
    return result


def workflow_check(root):
    path = root / ".github/workflows/ci.yml"
    text = path.read_text("utf-8")
    value = yaml.safe_load(text)
    if value.get("permissions") != {"contents": "read"}:
        raise ValueError("CI permissions incompatible")
    if any(
        term in text for term in ("pull_request_target", "secrets.", "upload-artifact", "write-all")
    ):
        raise ValueError("Privileged CI feature not permitted")
    if set(value["jobs"]) != {"offline", "postgres"}:
        raise ValueError("Required CI jobs missing")
    for job in value["jobs"].values():
        for step in job["steps"]:
            if "uses" in step and not re.fullmatch(r"actions/[a-z-]+@[a-f0-9]{40}", step["uses"]):
                raise ValueError("Pinned maintained actions required")
            if (
                step.get("uses", "").startswith("actions/checkout@")
                and step.get("with", {}).get("persist-credentials") is not False
            ):
                raise ValueError("CI checkout credentials must not persist")
    if not all(
        term in text
        for term in (
            "'3.11'",
            "requirements-ci.lock",
            "ruff check",
            "ruff format --check",
            "pytest",
            "integration smoke-postgres",
            "release smoke",
            "HF_HUB_OFFLINE",
            "HF_DATASETS_OFFLINE",
            "TRANSFORMERS_OFFLINE",
            "127.0.0.1:5432:5432",
        )
    ):
        raise ValueError("Required offline/SQL/release CI checks missing")
    return "STATIC_CHECK_PASS_HOSTED_RUN_NOT_VERIFIED"


def preflight(root, *, isolated=False):
    checks = []

    def check(name, operation):
        try:
            detail = operation()
            blocked = isinstance(detail, dict) and detail.get("blocked", False)
            checks.append(
                {"check": name, "status": "BLOCKED" if blocked else "PASS", "detail": detail}
            )
        except Exception:
            checks.append(
                {
                    "check": name,
                    "status": "BLOCKED",
                    "detail": "MISSING_OR_INCOMPATIBLE_CONFIGURATION",
                }
            )

    def configuration():
        if (
            sys.version_info[:2] != (3, 11)
            or Settings().environment == "production"
            or not __debug__
        ):
            raise ValueError("Local Python 3.11 required")
        rules = load(root)
        project = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
        if project["project"]["version"] != rules.project_version:
            raise ValueError("Project version mismatch")
        return rules.release_id

    def dependencies():
        pins = locked(root)
        incompatible = []
        for package, expected in pins.items():
            try:
                actual = metadata.version(package)
            except metadata.PackageNotFoundError:
                actual = None
            if actual != expected:
                incompatible.append({"package": package, "expected": expected, "installed": actual})
        if incompatible:
            return {"blocked": True, "dependencies": incompatible}
        for module in (
            "fastapi",
            "streamlit",
            "plotly",
            "sqlalchemy",
            "alembic",
            "psycopg",
            "sklearn",
            "torch",
            "transformers",
            "pyarrow",
        ):
            importlib.import_module(module)
        return {"exact_pins_verified": len(pins), "lock": "requirements-ci.lock"}

    def api():
        if isolated:
            settings = ApiSettings(
                mode="DEMO_ONLY", environment="test", api_key=None, principals=None
            )
            return "EXPLICIT_ISOLATED_DEMO_EPHEMERAL_CREDENTIALS"
        settings = ApiSettings()
        if settings.mode != "DEMO_ONLY" or not settings.credentials:
            raise ValueError("Explicit demo and role credentials required")
        if any(s != "synthetic_demo" for c in settings.credentials for s in c.source_ids):
            raise ValueError("Release principals must be synthetic only")
        if {c.role for c in settings.credentials} != {"ADMIN", "REVIEWER", "ANALYST"}:
            raise ValueError("All demo roles required")
        if not any(c.role == "REVIEWER" and c.can_view_text for c in settings.credentials):
            raise ValueError("Demo reviewer text permission required")
        from dashboard.api_client import Settings as DashboardSettings

        dashboard = DashboardSettings()
        principal = resolve(
            settings.credentials,
            dashboard.api_key.get_secret_value() if dashboard.api_key else None,
        )
        if principal is None or principal.role != "ANALYST" or principal.can_view_text:
            raise ValueError("Restricted dashboard ANALYST required")
        # Dedicated runtime ignores external DB URLs; it creates owned temporary SQLite.
        return "EXPLICIT_LOCAL_DEMO_ROLE_CREDENTIALS_AVAILABLE"

    def governance():
        from pfa.research.schemas import TEMPLATES
        from pfa.research.validation import validate_file

        source = load_registry(root / "configs/dataset_sources.yaml").source("synthetic_demo")
        if source.dataset_role != "SYNTHETIC":
            raise ValueError("Synthetic source required")
        for name in TEMPLATES:
            for suffix in (".csv", ".jsonl"):
                if validate_file(root / "templates/research" / (name + suffix), name)["records"]:
                    raise ValueError("Official research templates must remain blank")
        return {
            "source": source.source_id,
            "model": "MOCK_NO_TRAINED_ARTIFACT",
            "human_taxonomy_approval": "PENDING_NOT_REQUIRED_FOR_SYNTHETIC_DEMO",
            "research": "BLOCKED_PERMISSION_AND_EXPERIMENT",
            "holdout": "PROTECTED",
        }

    def security():
        result = scan(root)
        if result["status"] != "SECURITY_SCAN_PASS":
            raise ValueError("Repository scan failed")
        return {
            "status": result["status"],
            "tracked": result["tracked_files"],
            "candidates": result["candidate_files"],
        }

    check("configuration", configuration)
    check("dependencies", dependencies)
    check("api_and_credentials", api)
    check("governance", governance)
    check("ci", lambda: workflow_check(root))
    check("security", security)
    return {
        "status": "BLOCKED" if any(c["status"] == "BLOCKED" for c in checks) else "WARNING",
        "classification": "TECHNICAL_DEMO_ONLY",
        "scope": "ISOLATED" if isolated else "LOCAL_SERVICE",
        "checks": checks,
        "warnings": [
            "RESEARCH_AND_APPROVED_MODEL_UNAVAILABLE",
            "CI_HOSTED_RUN_NOT_VERIFIED",
            "BACKUP_RESTORE_REHEARSAL_NOT_VERIFIED",
        ],
        "database": "OWNED_TEMPORARY_SQLITE_CREATED_ONLY_BY_EXPLICIT_DEMO_COMMAND",
        "POSTGRES_CURRENT_RUN": "CONFIGURED_NOT_YET_VERIFIED"
        if os.environ.get("TEST_DATABASE_URL")
        else "NOT_VERIFIED",
        "POSTGRES_HISTORICAL": "VERIFIED_PER_STEP16_EVIDENCE",
        "dependency_audit_available": importlib.util.find_spec("pip_audit") is not None,
        "dependency_audit_executed": False,
        "pending_release_checks": ["synthetic_smoke", "manifest"],
        "analytics": "CONFIGURATION_VALIDATED_SMOKE_REQUIRED",
    }
