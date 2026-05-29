# -*- coding: utf-8 -*-
"""Helpers for rotating multiple upstream authentication header sets.

The gateway already stores authentication in ``auth_value``.  This module keeps
the storage shape backward-compatible while allowing ``auth_value`` to contain a
credential pool:

.. code-block:: json

    {
      "credential_pool": [
        {"headers": {"Authorization": "Bearer key-a"}},
        {"headers": {"Authorization": "Bearer key-b"}}
      ]
    }

Only header names and opaque slot ids are exposed by helpers. Header values are
never logged here.
"""

# Standard
from dataclasses import dataclass
import hashlib
import re
import threading
import time
from typing import Any, Dict, Iterable, Optional


CREDENTIAL_POOL_KEY = "credential_pool"
_DEFAULT_COOLDOWN_SECONDS = 300.0
_QUOTA_ERROR_RE = re.compile(r"(quota|rate.?limit|too many requests|insufficient|exceed|exceeded|额度|限额|余额不足)", re.IGNORECASE)


@dataclass(frozen=True)
class CredentialSlot:
    """One upstream credential option selected from a gateway auth pool."""

    slot_id: str
    headers: Dict[str, str]


class CredentialPoolState:
    """In-memory round-robin state with short-lived per-key cooldowns.

    The state is intentionally process-local and best-effort. It prevents a bad
    key from being hammered in a single worker without adding a DB migration or
    writing secret-derived state back to the database.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_index: Dict[str, int] = {}
        self._cooldowns: Dict[tuple[str, str], float] = {}

    def reset(self) -> None:
        """Clear all runtime rotation state. Intended for tests."""
        with self._lock:
            self._next_index.clear()
            self._cooldowns.clear()

    def select(self, pool_key: str, slots: list[CredentialSlot], now: Optional[float] = None) -> CredentialSlot:
        """Select the next non-cooled credential slot, falling back to round-robin.

        Args:
            pool_key: Stable key for one upstream pool, usually gateway id/name.
            slots: Candidate credential slots.
            now: Optional monotonic timestamp for deterministic tests.

        Returns:
            The selected credential slot.

        Raises:
            ValueError: If ``slots`` is empty.
        """
        if not slots:
            raise ValueError("credential pool has no usable slots")
        current = time.monotonic() if now is None else now
        with self._lock:
            start = self._next_index.get(pool_key, 0) % len(slots)
            for offset in range(len(slots)):
                idx = (start + offset) % len(slots)
                slot = slots[idx]
                if self._cooldowns.get((pool_key, slot.slot_id), 0.0) <= current:
                    self._next_index[pool_key] = (idx + 1) % len(slots)
                    return slot

            # If every key is cooled down, still return one deterministically so
            # callers can surface the real upstream error instead of failing here.
            slot = slots[start]
            self._next_index[pool_key] = (start + 1) % len(slots)
            return slot

    def mark_unavailable(self, pool_key: str, slot_id: str, cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS, now: Optional[float] = None) -> None:
        """Temporarily cool down one credential slot."""
        current = time.monotonic() if now is None else now
        with self._lock:
            self._cooldowns[(pool_key, slot_id)] = current + max(0.0, cooldown_seconds)


credential_pool_state = CredentialPoolState()


def is_credential_pool(auth_value: Any) -> bool:
    """Return True when ``auth_value`` contains a credential pool."""
    return isinstance(auth_value, dict) and isinstance(auth_value.get(CREDENTIAL_POOL_KEY), list)


def _stable_slot_id(headers: Dict[str, str], idx: int) -> str:
    material = "\n".join(f"{k.lower()}={v}" for k, v in sorted(headers.items()))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return f"key-{idx + 1}-{digest}"


def _coerce_headers(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if k and v is not None and str(v) != ""}


def extract_credential_slots(auth_value: Any) -> list[CredentialSlot]:
    """Extract usable credential slots from a decoded auth value."""
    if not is_credential_pool(auth_value):
        return []

    slots: list[CredentialSlot] = []
    for idx, item in enumerate(auth_value.get(CREDENTIAL_POOL_KEY) or []):
        if isinstance(item, dict) and "headers" in item:
            headers = _coerce_headers(item.get("headers"))
            configured_id = item.get("id") or item.get("name")
        else:
            headers = _coerce_headers(item)
            configured_id = None

        if not headers:
            continue
        slot_id = str(configured_id) if configured_id else _stable_slot_id(headers, idx)
        slots.append(CredentialSlot(slot_id=slot_id, headers=headers))

    return slots


def select_auth_headers(auth_value: Any, pool_key: str = "default", state: CredentialPoolState = credential_pool_state) -> tuple[Dict[str, str], Optional[str]]:
    """Return headers for a decoded auth value, rotating pools when present.

    Args:
        auth_value: Decoded auth dict. May be a normal header dict or a pool.
        pool_key: Stable namespace for runtime rotation state.
        state: State object, injectable for tests.

    Returns:
        ``(headers, slot_id)``. ``slot_id`` is ``None`` for non-pooled auth.
    """
    slots = extract_credential_slots(auth_value)
    if slots:
        slot = state.select(pool_key, slots)
        return dict(slot.headers), slot.slot_id
    return _coerce_headers(auth_value), None


def should_rotate_credential_on_error(error: BaseException | str | None) -> bool:
    """Heuristically decide whether an upstream error likely exhausted a key."""
    if error is None:
        return False
    text = str(error)
    if any(code in text for code in ("401", "403", "429")):
        return True
    return bool(_QUOTA_ERROR_RE.search(text))


def auth_headers_variants(auth_value: Any) -> Iterable[tuple[Dict[str, str], Optional[str]]]:
    """Yield every auth header variant in storage order.

    This is used by registration/refresh paths that only need one successful
    read-only discovery pass and should not mutate runtime round-robin state.
    """
    slots = extract_credential_slots(auth_value)
    if slots:
        for slot in slots:
            yield dict(slot.headers), slot.slot_id
        return
    yield _coerce_headers(auth_value), None
