"""Local repository scanning. Findings contain locations and rules, never matched values."""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from pfa.data.official_io import safe_path
from pfa.integration.contracts import load

PATTERNS = {
    "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "CREDENTIAL_URL": re.compile(
        r"\b(?:postgres(?:ql)?(?:\+psycopg)?|mysql|mongodb)://[^\s:/]+:[^\s@]+@", re.I
    ),
    "SERVICE_TOKEN": re.compile(
        r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}|sk-[A-Za-z0-9_-]{32,})\b"
    ),
    "LITERAL_SECRET": re.compile(
        r"""(?i)\b(?:[a-z0-9]+_)*(?:api_key|password|secret|token)["']?"""
        r"""\s*[=:]\s*["']([^"'\s]{12,})["']"""
    ),
    "SENSITIVE_SAMPLE": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "SENSITIVE_IDENTIFIER": re.compile(
        r"(?i)(?:phone|số điện thoại|citizen_id|cccd|cmnd)\W{0,8}\d{9,12}\b"
    ),
    "ENV_SECRET": re.compile(
        r"^\s*(?:export\s+)?[A-Z0-9_]*(?:API_KEY|PASSWORD|SECRET|TOKEN)"
        r"\s*[:=]\s*[A-Za-z0-9_+/=-]{12,}\s*$"
    ),
}
FORBIDDEN = {
    ".pkl",
    ".joblib",
    ".pt",
    ".pth",
    ".bin",
    ".safetensors",
    ".onnx",
    ".parquet",
    ".arrow",
    ".sqlite",
    ".db",
    ".dump",
    ".backup",
    ".xlsx",
    ".pem",
    ".key",
}


def inspect_file(root: Path, relative: str):
    path = safe_path(root / relative, root)
    if path.is_symlink() or not path.is_file():
        return [{"path": relative, "rule": "UNSAFE_FILE", "line": 0}]
    name = path.name
    forbidden = (
        path.suffix.lower() in FORBIDDEN
        or name == ".env"
        or (name.startswith(".env.") and name != ".env.example")
        or (
            relative.split("/")[0] in {"data", "reports", "models", "artifacts", "checkpoints"}
            and name != ".gitkeep"
        )
        or (
            path.suffix in {".csv", ".tsv", ".jsonl"}
            and relative
            not in {
                "tests/fixtures/public_service_feedback_synthetic.csv",
                "configs/permission_history.jsonl",
            }
            and not relative.startswith("templates/research/")
        )
    )
    if forbidden:
        return [{"path": relative, "rule": "PRIVATE_ARTIFACT", "line": 0}]
    if path.stat().st_size > 2 * 1024**2:
        return [{"path": relative, "rule": "OVERSIZED_UNSCANNED", "line": 0}]
    if relative == "tests/fixtures/public_service_feedback_synthetic.csv":
        from pfa.data.official import SYNTHETIC_FIXTURE_SHA256

        if hashlib.sha256(path.read_bytes()).hexdigest() != SYNTHETIC_FIXTURE_SHA256:
            return [{"path": relative, "rule": "SYNTHETIC_FIXTURE_TAMPERED", "line": 0}]
    try:
        content = path.read_text("utf-8-sig")
    except UnicodeError:
        return [{"path": relative, "rule": "BINARY_UNSCANNED", "line": 0}]
    if relative.startswith("templates/research/") and path.suffix in {".csv", ".jsonl"}:
        if (path.suffix == ".csv" and len(content.splitlines()) > 1) or (
            path.suffix == ".jsonl" and content.strip()
        ):
            return [{"path": relative, "rule": "POPULATED_RESEARCH_TEMPLATE", "line": 0}]
    findings = []
    for number, line in enumerate(content.splitlines(), 1):
        for rule, pattern in PATTERNS.items():
            matches = list(pattern.finditer(line))
            if rule == "SENSITIVE_SAMPLE":
                # Reserved domains are invented examples, not citizen contact details.
                matches = [
                    m
                    for m in matches
                    if not m.group()
                    .lower()
                    .endswith((".invalid", ".test", "@example.com", "@example.org", "@example.net"))
                ]
            if matches:
                findings.append(
                    {
                        "path": relative,
                        "rule": rule,
                        "line": number,
                        "line_sha256": hashlib.sha256(line.encode()).hexdigest(),
                    }
                )
    return findings


def scan(root: Path):
    def files(*options):
        result = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "ls-files", "-z", *options],
            cwd=root,
            capture_output=True,
            timeout=30,
        )
        if result.returncode:
            raise ValueError("Git inventory unavailable")
        return [p for p in result.stdout.decode("utf-8").split("\0") if p]

    tracked = files("--cached")
    candidates = sorted(set(tracked + files("--others", "--exclude-standard")))
    exclusions = [e.model_dump() for e in load(root).reviewed_exclusions]
    findings, reviewed = [], 0
    for path in candidates:
        try:
            found = inspect_file(root, path)
        except (ValueError, OSError):
            found = [{"path": path, "rule": "UNSAFE_FILE", "line": 0}]
        for item in found:
            excluded = any(
                e["path"] == item["path"]
                and e["rule"] == item["rule"]
                and e["line_sha256"] == item.get("line_sha256")
                and e.get("reason")
                for e in exclusions
            )
            if excluded:
                reviewed += 1
            else:
                findings.append({k: v for k, v in item.items() if k != "line_sha256"})
    return {
        "status": "SECURITY_SCAN_PASS" if not findings else "SECURITY_SCAN_FAIL",
        "tracked_files": len(tracked),
        "candidate_files": len(candidates),
        "coverage": "TRACKED_AND_UNIGNORED_CANDIDATES",
        "reviewed_findings": reviewed,
        "findings": findings,
        "matched_values_withheld": True,
        "limitations": "Heuristic local scan; cannot establish absence of PII or all secrets",
    }


def dependencies():
    """Explicit optional network operation: sends package metadata only, never project data."""
    executable = shutil.which("pip-audit")
    if executable is None:
        return {"status": "DEPENDENCY_AUDIT_NOT_AVAILABLE", "reason": "pip-audit not installed"}, 4
    try:
        result = subprocess.run(
            [executable, "--format=json", "--progress-spinner=off"],
            capture_output=True,
            timeout=120,
        )
        payload = json.loads(result.stdout)
        packages = payload["dependencies"]
        skipped = sum(bool(p.get("skip_reason")) for p in packages)
        vulnerabilities = [
            {
                "package": p["name"],
                "version": p["version"],
                "advisories": [v["id"] for v in p.get("vulns", [])],
            }
            for p in packages
            if p.get("vulns")
        ]
        if result.returncode not in {0, 1} or (result.returncode == 1 and not vulnerabilities):
            raise ValueError
        if skipped and not vulnerabilities:
            return {"status": "DEPENDENCY_AUDIT_INCOMPLETE", "skipped_packages": skipped}, 4
        return {
            "status": "DEPENDENCY_VULNERABILITIES_FOUND"
            if vulnerabilities
            else "DEPENDENCY_AUDIT_PASS",
            "vulnerabilities": vulnerabilities,
        }, int(bool(vulnerabilities)) * 2
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return {
            "status": "DEPENDENCY_AUDIT_NOT_AVAILABLE",
            "reason": "Tool or advisory service unavailable",
        }, 4
