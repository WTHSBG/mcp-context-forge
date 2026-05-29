# -*- coding: utf-8 -*-
"""Unit tests for upstream MCP credential pool routing."""

# Third-Party
import pytest

# First-Party
from mcpgateway.utils.credential_pool import (
    CredentialPoolState,
    auth_headers_variants,
    extract_credential_slots,
    select_auth_headers,
    should_rotate_credential_on_error,
)
from mcpgateway.utils.gateway_access import build_gateway_auth_headers


class _Gateway:
    def __init__(self, auth_value):
        self.id = "gw-test"
        self.auth_type = "authheaders"
        self.auth_value = auth_value


def test_select_auth_headers_round_robins_pool_without_exposing_values():
    state = CredentialPoolState()
    auth_value = {
        "credential_pool": [
            {"id": "a", "headers": {"Authorization": "Bearer first"}},
            {"id": "b", "headers": {"Authorization": "Bearer second"}},
        ]
    }

    first_headers, first_slot = select_auth_headers(auth_value, "gateway:test", state)
    second_headers, second_slot = select_auth_headers(auth_value, "gateway:test", state)
    third_headers, third_slot = select_auth_headers(auth_value, "gateway:test", state)

    assert first_headers == {"Authorization": "Bearer first"}
    assert first_slot == "a"
    assert second_headers == {"Authorization": "Bearer second"}
    assert second_slot == "b"
    assert third_headers == {"Authorization": "Bearer first"}
    assert third_slot == "a"


def test_credential_pool_skips_cooled_down_slot():
    state = CredentialPoolState()
    auth_value = {
        "credential_pool": [
            {"id": "a", "headers": {"Authorization": "Bearer first"}},
            {"id": "b", "headers": {"Authorization": "Bearer second"}},
        ]
    }
    slots = extract_credential_slots(auth_value)

    state.mark_unavailable("gateway:test", "a", cooldown_seconds=60, now=100)

    selected = state.select("gateway:test", slots, now=101)

    assert selected.slot_id == "b"
    assert selected.headers == {"Authorization": "Bearer second"}


@pytest.mark.parametrize(
    "message",
    [
        "HTTP 429 Too Many Requests",
        "quota exceeded for this token",
        "额度已用完",
    ],
)
def test_should_rotate_credential_on_quota_like_errors(message):
    assert should_rotate_credential_on_error(RuntimeError(message))


def test_auth_headers_variants_preserves_pool_order():
    auth_value = {
        "credential_pool": [
            {"id": "a", "headers": {"Authorization": "Bearer first"}},
            {"id": "b", "headers": {"Authorization": "Bearer second"}},
        ]
    }

    variants = list(auth_headers_variants(auth_value))

    assert variants == [
        ({"Authorization": "Bearer first"}, "a"),
        ({"Authorization": "Bearer second"}, "b"),
    ]


def test_build_gateway_auth_headers_uses_credential_pool():
    auth_value = {
        "credential_pool": [
            {"id": "a", "headers": {"Authorization": "Bearer first"}},
            {"id": "b", "headers": {"Authorization": "Bearer second"}},
        ]
    }

    headers = build_gateway_auth_headers(_Gateway(auth_value))

    assert headers == {"Authorization": "Bearer first"}
