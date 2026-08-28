"""Tests for Desktop Extension user-config handling."""

from unittest.mock import patch

import pytest

from garmin_mcp import (
    _normalize_optional_user_config,
    init_api,
    tokenstore,
)
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


@pytest.mark.parametrize(
    ("value", "key"),
    [
        ("${user_config.garmin_email}", "garmin_email"),
        ("${user_config.garmin_password}", "garmin_password"),
    ],
)
def test_unresolved_optional_user_config_is_treated_as_unset(value, key):
    assert _normalize_optional_user_config(value, key) is None


def test_real_value_containing_template_syntax_is_preserved():
    value = "secret-${not_a_user_config_placeholder}"

    assert _normalize_optional_user_config(value, "garmin_password") == value


@patch("garmin_mcp.is_interactive_terminal", return_value=False)
@patch("garmin_mcp.Garmin")
def test_unresolved_credentials_do_not_trigger_login(mock_garmin, _mock_terminal):
    mock_garmin.return_value.login.side_effect = FileNotFoundError

    result = init_api(
        "${user_config.garmin_email}",
        "${user_config.garmin_password}",
    )

    assert result is None
    mock_garmin.assert_called_once_with(is_cn=False)
    mock_garmin.return_value.login.assert_called_once_with(tokenstore)


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (FileNotFoundError(), "OAuth tokens not found"),
        (
            GarminConnectAuthenticationError("expired"),
            "OAuth tokens are invalid or expired",
        ),
        (
            GarminConnectTooManyRequestsError("429"),
            "rate-limited OAuth token validation",
        ),
        (
            GarminConnectConnectionError("proxy disconnected"),
            "network request failed",
        ),
    ],
)
@patch("garmin_mcp.is_interactive_terminal", return_value=False)
@patch("garmin_mcp.Garmin")
def test_noninteractive_token_failures_have_specific_diagnostics(
    mock_garmin,
    _mock_terminal,
    error,
    expected_message,
    capsys,
):
    mock_garmin.return_value.login.side_effect = error

    result = init_api(None, None)

    assert result is None
    assert expected_message in capsys.readouterr().err
