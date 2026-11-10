"""Public source inventory, immutable publication and tamper verification; no archive upload."""

import subprocess
import sys
from datetime import UTC, datetime

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM
from pfa.release.config import load
from pfa.research.schemas import TEMPLATES


def inventory(root):
    # Explicit public allowlist, independent of whether this workspace has been committed.
    files = set()
    for directory in ("src/pfa", "dashboard", "migrations", "tests"):
        files.update(p for p in (root / directory).rglob("*.py") if "__pycache__" not in p.parts)
    files.update((root / "docs").rglob("*.md"))
    files.discard(
        root / "docs/STEP17_VERIFICATION.md"
    )  # Generation attestation, not a build input.
    files.update((root / "scripts").glob("*.ps1"))
    files.add(root / "templates/research/README.md")
    for name in TEMPLATES:
        for suffix in (".csv", ".jsonl", ".schema.json"):
            files.add(root / "templates/research" / (name + suffix))
    for name in (
        "privacy_audit_synthetic.json",
        "uit_vsfc_synthetic.json",
        "public_service_feedback_synthetic.csv",
    ):
        files.add(root / "tests/fixtures" / name)
    for name in (
        "taxonomy_v1",
        "dataset_sources",
        "evaluation_v1",
        "api_v1",
        "analytics_v1",
        "research_protocol_v1",
        "integration_v1",
        "release_v1",
    ):
        files.add(root / f"configs/{name}.yaml")
    for name in (
        "pyproject.toml",
        "requirements-ci.lock",
        "requirements-audit.lock",
        "README.md",
        "alembic.ini",
        ".env.example",
        ".gitignore",
        ".github/workflows/ci.yml",
        ".streamlit/config.toml",
    ):
        files.add(root / name)
    if any(not p.is_file() for p in files):
        raise ValueError("Required public release file missing")
    return {
        p.relative_to(root).as_posix(): store.file_checksum(store.safe_path(p, root))
        for p in sorted(files)
        if p.is_file()
    }


def build(root):
    rules = load(root)
    for name in (
        "DATASET_CARD_DEMO.md",
        "MODEL_CARD_DEMO.md",
        "DEMO_QUICKSTART.md",
        "TECHNICAL_HANDOVER.md",
        "RELEASE_CHECKLIST.md",
    ):
        if not (root / "docs" / name).is_file():
            raise ValueError("Release documentation missing")
    files = inventory(root)
    stable = {
        "release": rules.model_dump(),
        "artifacts": files,
        "taxonomy_checksum": CHECKSUM,
        "model_provenance": {
            "provider": "MOCK_FIXTURE",
            "trained": False,
            "calibrated": False,
            "scores": None,
            "requires_review": True,
        },
        "fixture_status": "SYNTHETIC_NOT_RESEARCH_GOLD",
    }
    git = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        capture_output=True,
        timeout=10,
    )
    revision = git.stdout.decode().strip() if git.returncode == 0 else None
    return {
        "schema_version": "release-manifest-1",
        "content": stable,
        "content_sha256": store.digest(stable),
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "git_revision": revision,
        "git_revision_covers_worktree": False,
        "test_evidence_references": ["docs/STEP17_VERIFICATION.md", "docs/STEP16_VERIFICATION.md"],
        "test_evidence_reexecuted_by_manifest_command": False,
        "packaged_archive": False,
        "published": False,
    }


def verify(root, manifest):
    content = manifest["content"]
    if (
        manifest["schema_version"] != "release-manifest-1"
        or store.digest(content) != manifest["content_sha256"]
    ):
        raise ValueError("Manifest integrity mismatch")
    expected = build(root)["content"]
    if content != expected:
        raise ValueError("Release source/configuration or provenance changed")
    return {
        "status": "RELEASE_MANIFEST_VERIFIED",
        "release_id": content["release"]["release_id"],
        "content_sha256": manifest["content_sha256"],
        "artifact_count": len(content["artifacts"]),
        "classification": "TECHNICAL_DEMO_ONLY",
        "packaged_archive": False,
    }


def publish(root, output):
    from pfa.integration.security_checks import scan

    if scan(root)["status"] != "SECURITY_SCAN_PASS":
        raise ValueError("Resolve scanner findings before release inventory publication")
    output = store.safe_path(
        output if output.is_absolute() else root / output, root / "reports/releases"
    )
    value = build(root)
    store.publish(output, {"manifest.json": value})
    documents, checksum = store.bundle(output)
    return {
        **verify(root, documents["manifest.json"]),
        "bundle_sha256": checksum,
        "manifest_file_sha256": store.file_checksum(output / "manifest.json"),
        "output": output.relative_to(root).as_posix(),
    }
