"""Explicit lock-only advisory lookup; never invoked by offline smoke or preflight."""

import importlib.util
import json
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from importlib.metadata import version as installed_version
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from pfa.annotation import pilot_store as store
from pfa.release.preflight import locked


def run(root):
    pins = locked(root)
    project = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))["project"]
    direct = {canonicalize_name(Requirement(item).name) for item in project["dependencies"]}
    for extra in ("dev", "data", "phobert", "api", "dashboard"):
        direct.update(
            canonicalize_name(Requirement(item).name)
            for item in project["optional-dependencies"][extra]
        )
    evidence = {
        "dependency_set": "requirements-ci.lock",
        "lock_sha256": store.file_checksum(root / "requirements-ci.lock"),
        "audited_pins": [
            {
                "package": name,
                "version": version,
                "advisory_query_version": Version(version).public,
                "kind": "DIRECT" if canonicalize_name(name) in direct else "TRANSITIVE",
            }
            for name, version in pins.items()
        ],
        "scope": "RELEASE_LOCK_PUBLIC_VERSIONS_LOCAL_BUILD_TAGS_RECORDED_SEPARATELY",
        "executed_at": datetime.now(UTC).isoformat(),
    }
    if importlib.util.find_spec("pip_audit") is None:
        return {**evidence, "status": "AUDIT_NOT_AVAILABLE", "executed": False}, 4
    try:
        with TemporaryDirectory(prefix="pfa-release-audit-") as temporary:
            path = Path(temporary) / "public-requirements.txt"
            path.write_text(
                "\n".join(f"{n}=={Version(v).public}" for n, v in pins.items()) + "\n",
                encoding="utf-8",
            )
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_audit",
                    "--no-deps",
                    "--disable-pip",
                    "-r",
                    str(path),
                    "--format=json",
                    "--progress-spinner=off",
                ],
                capture_output=True,
                timeout=120,
            )
            payload = json.loads(process.stdout)
        vulnerabilities = [
            {
                "package": p["name"],
                "version": p["version"],
                "advisories": [
                    {"id": v["id"], "fix_versions": v.get("fix_versions", [])}
                    for v in p.get("vulns", [])
                ],
            }
            for p in payload["dependencies"]
            if p.get("vulns")
        ]
        skipped = [p["name"] for p in payload["dependencies"] if p.get("skip_reason")]
        returned = {
            (canonicalize_name(p["name"]), p.get("version")) for p in payload["dependencies"]
        }
        missing = [
            n for n, v in pins.items() if (canonicalize_name(n), Version(v).public) not in returned
        ]
        if process.returncode not in {0, 1} or (process.returncode == 1 and not vulnerabilities):
            raise ValueError("Advisory lookup failed")
        status = (
            "FINDINGS"
            if vulnerabilities
            else "AUDIT_NOT_AVAILABLE"
            if skipped or missing
            else "PASS"
        )
        return {
            **evidence,
            "status": status,
            "executed": True,
            "vulnerabilities": vulnerabilities,
            "skipped_packages": skipped,
            "missing_query_results": missing,
            "checker_version": installed_version("pip-audit"),
        }, {"PASS": 0, "FINDINGS": 2, "AUDIT_NOT_AVAILABLE": 4}[status]
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return {
            **evidence,
            "status": "AUDIT_NOT_AVAILABLE",
            "executed": False,
            "reason": "TOOL_OR_ADVISORY_SERVICE_UNAVAILABLE",
        }, 4
