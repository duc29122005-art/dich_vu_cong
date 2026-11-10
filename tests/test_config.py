import pytest
from pydantic import ValidationError

from pfa.core.config import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("PFA_ENVIRONMENT", "PFA_LOG_LEVEL", "PFA_PROJECT_ROOT"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_and_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.data_dir == tmp_path / "data"
    assert all(path.is_relative_to(tmp_path) for path in settings.required_directories)


def test_dotenv_and_environment_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PFA_ENVIRONMENT=test\nPFA_LOG_LEVEL=WARNING\n")
    assert Settings().environment == "test"
    monkeypatch.setenv("PFA_LOG_LEVEL", "ERROR")
    assert Settings().log_level == "ERROR"


@pytest.mark.parametrize(
    "values",
    [
        {"environment": "invalid"},
        {"log_level": "INVALID"},
        {"project_root": "nonexistent-project-root"},
    ],
)
def test_invalid_configuration(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
