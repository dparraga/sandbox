"""Cloud boundary; live access remains disabled until included-only use is verified.

No credential discovery, login, network transport or automatic retries occur here.
The injected transport supports local integration tests; it is not a configured
production authentication or billing mechanism.
"""

import json
import math
from typing import Literal, Protocol


MODEL = "gpt-6-luna"
CloudCategory = Literal[
    "included_only_unverified", "authentication", "network", "quota",
    "model", "unavailable", "unknown_outcome", "invalid_response",
]
_CATEGORIES = frozenset(CloudCategory.__args__)


class CloudUnavailable(Exception):
    """Safe report category; never retain transport text or private request data."""

    def __init__(self, category: CloudCategory):
        if category not in _CATEGORIES:
            raise ValueError("Unknown cloud failure category")
        self.category = category
        super().__init__(category)


class CloudTransport(Protocol):
    """Injected test boundary. A future live transport must verify the full grant.

    Availability must cover app-owned authentication, included-only authorization
    and exact Luna availability. Recognition must return completed output only;
    an interrupted request raises unknown_outcome, never an unreadable result.
    """

    def check_available(self) -> None: ...

    def recognize(self, request: dict) -> str | dict: ...


def parse_response(raw: str | dict) -> dict:
    """Reject duplicate keys, nonfinite numbers and non-object model output."""
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError("Nonfinite value")

    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("Nonfinite value")
        return value

    try:
        # Round-trip injected dictionaries too, so non-JSON/nonfinite values fail.
        text = json.dumps(raw, allow_nan=False) if isinstance(raw, dict) else raw
        result = json.loads(text, object_pairs_hook=object_pairs,
                            parse_constant=invalid_constant, parse_float=finite_float)
        if not isinstance(result, dict):
            raise ValueError("Expected object")
    except (TypeError, ValueError, RecursionError):
        raise CloudUnavailable("invalid_response") from None
    return result


class CloudClient:
    """Unavailable by default; injectable for deterministic offline verification."""

    def __init__(self, transport: CloudTransport | None = None):
        self._transport = transport

    def check_available(self) -> None:
        if self._transport is None:
            raise CloudUnavailable("included_only_unverified")
        try:
            self._transport.check_available()
        except CloudUnavailable:
            raise
        except Exception:
            raise CloudUnavailable("unavailable") from None

    def recognize(self, request: dict) -> dict:
        self.check_available()
        if (not isinstance(request, dict) or request.get("model") != MODEL
                or request.get("store") is not False
                or request.get("stream") is not True
                or not isinstance(request.get("input"), list)):
            raise CloudUnavailable("invalid_response")
        try:
            raw = self._transport.recognize(request)
        except CloudUnavailable:
            raise
        except Exception:
            # Once dispatch starts, even a timeout may have completed remotely.
            raise CloudUnavailable("unknown_outcome") from None
        return parse_response(raw)
