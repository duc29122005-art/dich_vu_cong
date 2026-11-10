import os
import subprocess
import sys
from unittest.mock import patch

from pfa.cli import doctor
from pfa.core.config import Settings


def run_cli(root, *arguments, **variables):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PFA_")}
    environment.update(PFA_PROJECT_ROOT=str(root), **variables)
    return subprocess.run(
        [sys.executable, "-m", "pfa.cli", *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_doctor_success_and_directory_setup(tmp_path):
    settings = Settings(_env_file=None, project_root=tmp_path)
    for directory in settings.required_directories:
        directory.mkdir(parents=True, exist_ok=True)
    result = run_cli(tmp_path, "doctor")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS Configuration" in result.stdout
    assert "WARN No .env" in result.stdout
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_missing_directories_fail(tmp_path):
    result = run_cli(tmp_path, "doctor")
    assert result.returncode == 1
    assert "FAIL Directory" in result.stdout


def test_invalid_environment_is_redacted(tmp_path):
    result = run_cli(tmp_path, "doctor", PFA_ENVIRONMENT="private-sentinel")
    assert result.returncode == 1
    assert "private-sentinel" not in result.stdout + result.stderr


def test_unknown_command(tmp_path):
    assert run_cli(tmp_path, "unknown").returncode == 2


def test_permission_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PFA_ENVIRONMENT", "test")
    monkeypatch.setenv("PFA_LOG_LEVEL", "INFO")
    for directory in Settings().required_directories:
        directory.mkdir(parents=True, exist_ok=True)
    with patch("pfa.cli.TemporaryFile", side_effect=PermissionError):
        assert doctor() == 1
    assert "FAIL Read/write permissions" in capsys.readouterr().out
