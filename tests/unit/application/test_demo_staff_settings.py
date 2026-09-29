"""Configuration must fail closed before the demo API starts."""

from uuid import uuid4

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_demo_mode_defaults_to_disabled_production() -> None:
    settings = Settings(debug=False, _env_file=None)
    assert settings.app_env == "production"
    assert settings.demo_staff_auth_enabled is False
    assert settings.demo_staff_ticket_ids == []


def test_explicit_local_demo_with_allowlist_is_valid() -> None:
    ticket_id = uuid4()
    settings = Settings(
        app_env="local",
        demo_staff_auth_enabled=True,
        demo_staff_ticket_ids=[ticket_id],
        debug=False,
        _env_file=None,
    )
    assert settings.demo_staff_ticket_ids == [ticket_id]


def test_local_demo_reads_json_allowlist_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket_id = uuid4()
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DEMO_STAFF_AUTH_ENABLED", "true")
    monkeypatch.setenv("DEMO_STAFF_TICKET_IDS", f'["{ticket_id}"]')
    settings = Settings(debug=False, _env_file=None)
    assert settings.demo_staff_ticket_ids == [ticket_id]


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_production_or_unknown_environment_cannot_enable_demo(app_env: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env=app_env,
            demo_staff_auth_enabled=True,
            demo_staff_ticket_ids=[uuid4()],
            debug=False,
            _env_file=None,
        )


def test_enabled_demo_requires_nonempty_allowlist() -> None:
    with pytest.raises(ValidationError, match="DEMO_STAFF_TICKET_IDS"):
        Settings(app_env="local", demo_staff_auth_enabled=True, debug=False, _env_file=None)
