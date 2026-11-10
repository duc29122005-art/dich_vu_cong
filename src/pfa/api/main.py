"""Uvicorn import target. Defaults to unavailable APPROVED_MODEL mode, never demo."""

from pfa.api.app_factory import create_app

app = create_app()
