"""Exact Luna cloud boundary; subscription-only permission fails closed."""

import json
import math
import re
import time
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


MODEL = "gpt-6-luna"
CloudCategory = Literal[
    "included_only_unverified", "authentication", "network", "quota",
    "model", "unavailable", "unknown_outcome", "invalid_response",
]
_CATEGORIES = frozenset(CloudCategory.__args__)
_DIAGNOSTIC_ENUMS = {
    "operation": {"availability", "credentials", "token_refresh", "token_validation", "model_catalog", "inference"},
    "response_shape": {"error_object", "detail_only", "json_object", "non_object", "non_json", "too_large", "empty"},
    "request_state": {"not_sent", "rejected", "unknown", "invalid_response"},
    "detail": {"json", "unexpected_shape", "schema", "incomplete", "empty_output", "noncompleted_status",
               "request_shape", "refusal", "unexpected_output"},
}
_SERVICE_CODES = {
    "subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable",
    "subscription_sharing_user_unavailable", "subscription_sharing_user_not_eligible",
    "subscription_sharing_unsupported_capability", "subscription_sharing_route_not_supported",
    "subscription_sharing_invalid_user", "chatpass_v2_scope_not_authorized",
    "chatpass_v2_invalid_authorization_context", "rate_limit_exceeded", "invalid_token",
    "invalid_client", "invalid_grant", "invalid_refresh_token", "token_expired",
    "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused",
    "model_not_found", "model_not_available", "insufficient_quota", "server_error",
    "internal_server_error", "invalid_request_error", "permission_denied", "unrecognized",
}
_EXCEPTION_TYPES = {
    "OSError", "PermissionError", "FileNotFoundError", "TimeoutError", "URLError", "HTTPError",
    "ConnectionError", "ConnectionResetError", "SSLError", "ValueError", "TypeError", "KeyError",
    "AttributeError", "UnicodeError", "UnicodeDecodeError", "JSONDecodeError", "RecursionError",
    "RuntimeError", "InvalidTokenError", "InvalidSignatureError", "ExpiredSignatureError",
    "InvalidAudienceError", "InvalidIssuerError", "InvalidIssuedAtError", "ImmatureSignatureError",
    "MissingRequiredClaimError", "DecodeError", "InvalidAlgorithmError", "PyJWKError", "other",
}


def sanitize_diagnostic(value):
    """Copy only bounded, nonsecret diagnostic fields; never retain raw messages."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, choices in _DIAGNOSTIC_ENUMS.items():
        item = value.get(key)
        if isinstance(item, str) and item in choices:
            result[key] = item
    status = value.get("http_status")
    if type(status) is int and 100 <= status <= 599:
        result["http_status"] = status
    if "service_code" in value:
        code = value["service_code"]
        result["service_code"] = code if isinstance(code, str) and code in _SERVICE_CODES else "unrecognized"
    request_id = value.get("request_id")
    if isinstance(request_id, str) and re.fullmatch(r"req_[0-9a-fA-F]{32}", request_id):
        result["request_id"] = request_id
    if "exception_type" in value:
        name = value["exception_type"]
        result["exception_type"] = name if isinstance(name, str) and name in _EXCEPTION_TYPES else "other"
    return result


def _response_diagnostic(value, *, operation, http_status=None, request_id=None):
    diagnostic = {"operation": operation, "http_status": http_status, "request_id": request_id}
    if isinstance(value, (bytes, str)):
        if not value:
            return sanitize_diagnostic({**diagnostic, "response_shape": "empty"})
        if len(value) > 65536:
            return sanitize_diagnostic({**diagnostic, "response_shape": "too_large"})
        try:
            value = json.loads(value)
        except (ValueError, UnicodeError, RecursionError):
            return sanitize_diagnostic({**diagnostic, "response_shape": "non_json"})
    if not isinstance(value, dict):
        return sanitize_diagnostic({**diagnostic, "response_shape": "non_object"})
    error = value.get("error")
    diagnostic["response_shape"] = ("error_object" if isinstance(error, dict) else
                                     "detail_only" if "detail" in value and "error" not in value else "json_object")
    code = error.get("code") if isinstance(error, dict) else error if error is not None else value.get("code")
    if code is not None:
        diagnostic["service_code"] = code
    return sanitize_diagnostic(diagnostic)


class CloudUnavailable(Exception):
    """Safe report category; never retain transport text or private request data."""

    def __init__(self, category: CloudCategory, *, diagnostic=None):
        if category not in _CATEGORIES:
            raise ValueError("Unknown cloud failure category")
        self.category = category
        self.diagnostic = sanitize_diagnostic(diagnostic)
        super().__init__(category)


class KnownRequestRejected(CloudUnavailable):
    """Inference was rejected or prevented before dispatch; manual retry is safe."""


InvalidResponseDetail = Literal[
    "json", "unexpected_shape", "schema", "incomplete", "empty_output",
    "noncompleted_status", "request_shape", "refusal", "unexpected_output",
]


class InvalidResponse(CloudUnavailable):
    """Bounded diagnostic reason; contains no provider text or private content."""

    def __init__(self, detail: InvalidResponseDetail, *, diagnostic=None):
        if detail not in InvalidResponseDetail.__args__:
            raise ValueError("Unknown invalid response detail")
        self.detail = detail
        super().__init__("invalid_response", diagnostic={"request_state": "not_sent" if detail == "request_shape" else "invalid_response",
                                                        **sanitize_diagnostic(diagnostic), "detail": detail})


class CloudTransport(Protocol):
    """Subscription transport contract; deterministic tests may inject a transport.

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
    except (TypeError, ValueError, RecursionError):
        raise InvalidResponse("json") from None
    if not isinstance(result, dict):
        raise InvalidResponse("unexpected_shape")
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
        except CloudUnavailable as error:
            error.diagnostic = sanitize_diagnostic({"operation": "availability", **error.diagnostic})
            raise
        except Exception as error:
            raise CloudUnavailable("unavailable", diagnostic={"operation": "availability",
                                   "exception_type": type(error).__name__}) from None

    def recognize(self, request: dict) -> dict:
        try:
            self.check_available()
        except CloudUnavailable as error:
            raise KnownRequestRejected(error.category, diagnostic={**error.diagnostic, "request_state": "not_sent"}) from None
        if (not isinstance(request, dict) or request.get("model") != MODEL
                or request.get("store") is not False
                or request.get("stream") is not True
                or not isinstance(request.get("input"), list)):
            raise InvalidResponse("request_shape")
        try:
            raw = self._transport.recognize(request)
        except CloudUnavailable:
            raise
        except Exception as error:
            # Once dispatch starts, even a timeout may have completed remotely.
            raise CloudUnavailable("unknown_outcome", diagnostic={"operation": "inference",
                                   "exception_type": type(error).__name__}) from None
        try:
            return parse_response(raw)
        except InvalidResponse as error:
            error.diagnostic = sanitize_diagnostic({"operation": "inference", **error.diagnostic})
            raise


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _service_failure(error, status=None, *, diagnostic=None):
    diagnostic = {**sanitize_diagnostic(diagnostic), "request_state": "rejected"}
    code = error.get("code") if isinstance(error, dict) else None
    if code == "subscription_sharing_usage_limit_exceeded":
        return CloudUnavailable("quota", diagnostic=diagnostic)
    if code in ("subscription_sharing_invalid_user", "chatpass_v2_scope_not_authorized",
                "chatpass_v2_invalid_authorization_context") or status == 401:
        return KnownRequestRejected("authentication", diagnostic=diagnostic)
    if code in ("model_not_found", "model_not_available"):
        return KnownRequestRejected("model", diagnostic=diagnostic)
    if status is not None and status >= 500 and code not in (
            "subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable"):
        return CloudUnavailable("unknown_outcome", diagnostic={**diagnostic, "request_state": "unknown"})
    return KnownRequestRejected("unavailable", diagnostic=diagnostic)


def _stream_lines(response):
    """Bound total bytes, line length and streaming time, including slow drips."""
    total, pending = 0, b""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        chunk = response.read1(65536)
        total += len(chunk)
        if not chunk or total > 2_097_152:
            raise CloudUnavailable("unknown_outcome")
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            if len(line) > 65536:
                raise CloudUnavailable("unknown_outcome")
            yield line.decode("utf-8").rstrip("\r")
        if len(pending) > 65536:
            raise CloudUnavailable("unknown_outcome")
    raise CloudUnavailable("unknown_outcome")


class SubscriptionTransport:
    """Supported OAuth HTTP/SSE route with no retries or alternate billing.

    The protected confirmation records the user's verified provider configuration
    for this connection; it is not a cryptographic service billing attestation.
    No other billing path or automatic request retries exist.
    """

    def __init__(self, store, *, billing_guard=None, opener=None):
        self.store = store
        if billing_guard is None:
            from .subscription_auth import SubscriptionOnlyGuard
            billing_guard = SubscriptionOnlyGuard(store)
        self.billing_guard = billing_guard
        self._opener = opener if opener is not None else build_opener(_NoRedirect)
        self._catalog_checked = False

    def _permission(self):
        if self.billing_guard is None:
            raise CloudUnavailable("included_only_unverified")
        self.billing_guard.check_available()

    def _open(self, request, *, dispatched=False):
        operation = "inference" if dispatched else "model_catalog"
        try:
            return self._opener.open(request, timeout=60)
        except HTTPError as error:
            raw = b""
            try:
                raw = error.read(65537)
                body = parse_response(raw.decode()) if len(raw) <= 65536 else {}
            except (CloudUnavailable, UnicodeError):
                body = {}
            finally:
                error.close()
            diagnostic = _response_diagnostic(raw, operation=operation, http_status=error.code,
                                               request_id=error.headers.get("x-request-id") if error.headers else None)
            raise _service_failure(body.get("error"), error.code, diagnostic=diagnostic) from None
        except (URLError, OSError, TimeoutError) as error:
            raise CloudUnavailable("unknown_outcome" if dispatched else "network", diagnostic={
                "operation": operation, "exception_type": type(error).__name__}) from None

    def check_available(self):
        self._permission()
        if self._catalog_checked:
            return
        from .subscription_auth import access_token
        token = access_token(self.store)
        request = Request("https://api.openai.com/v1/models",
                          headers={"Authorization": "Bearer " + token,
                                   "Accept": "application/json"})
        try:
            with self._open(request) as response:
                raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise CloudUnavailable("unavailable")
            catalog = parse_response(raw.decode())
            models = catalog.get("models", [])
            if not isinstance(models, list) or not any(
                    isinstance(item, dict) and item.get("slug") == MODEL for item in models):
                raise CloudUnavailable("model")
            self._catalog_checked = True
        except CloudUnavailable as error:
            error.diagnostic = sanitize_diagnostic({"operation": "model_catalog", **error.diagnostic})
            raise
        except (OSError, UnicodeError) as error:
            raise CloudUnavailable("network", diagnostic={"operation": "model_catalog",
                                   "exception_type": type(error).__name__}) from None

    def recognize(self, request):
        try:
            self.check_available()
        except CloudUnavailable as error:
            raise KnownRequestRejected(error.category, diagnostic={"operation": "inference", **error.diagnostic,
                                                                  "request_state": "not_sent"}) from None
        # Defend direct transport use as well as CloudClient callers.
        if (not isinstance(request, dict) or request.get("model") != MODEL or request.get("store") is not False
                or request.get("stream") is not True or not isinstance(request.get("input"), list)):
            raise InvalidResponse("request_shape")
        from .subscription_auth import access_token
        try:
            token = access_token(self.store)
        except CloudUnavailable as error:
            raise KnownRequestRejected(error.category, diagnostic={"operation": "inference", **error.diagnostic,
                                                                  "request_state": "not_sent"}) from None
        wire = Request("https://api.openai.com/v1/responses",
                       data=json.dumps(request, allow_nan=False).encode(),
                       headers={"Authorization": "Bearer " + token,
                                "Content-Type": "application/json", "Accept": "text/event-stream"})
        stream_diagnostic = {"operation": "inference"}
        try:
            with self._open(wire, dispatched=True) as response:
                headers = getattr(response, "headers", None)
                stream_diagnostic = sanitize_diagnostic({"operation": "inference",
                    "http_status": getattr(response, "status", None),
                    "request_id": headers.get("x-request-id") if headers else None})
                data = []
                streamed = {}
                output_problem = None
                for line in _stream_lines(response):
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip(" "))
                    if line or not data:
                        continue
                    try:
                        event = parse_response("\n".join(data))
                    except CloudUnavailable:
                        diagnostic = _response_diagnostic("\n".join(data), operation="inference")
                        raise CloudUnavailable("unknown_outcome", diagnostic={**stream_diagnostic, **diagnostic}) from None
                    data = []
                    kind = event.get("type")
                    result = event.get("response", {})
                    if kind in ("response.output_text.delta", "response.output_text.done"):
                        indices = (event.get("output_index"), event.get("content_index"))
                        text = event.get("delta" if kind.endswith(".delta") else "text")
                        if (any(type(index) is not int or index < 0 for index in indices)
                                or not isinstance(text, str)):
                            output_problem = "unexpected_shape"
                            continue
                        part = streamed.setdefault(indices, {"deltas": [], "done": None})
                        if kind.endswith(".done"):
                            if part["done"] is not None and part["done"] != text:
                                output_problem = "unexpected_shape"
                            part["done"] = text
                        else:
                            if part["done"] is not None:
                                output_problem = "unexpected_shape"
                            part["deltas"].append(text)
                        continue
                    if isinstance(kind, str) and kind.startswith("response.refusal."):
                        output_problem = "refusal"
                    if kind in ("response.output_item.added", "response.output_item.done"):
                        item = event.get("item")
                        if not isinstance(item, dict) or item.get("type") not in ("message", "reasoning"):
                            output_problem = "unexpected_output"
                    if kind in ("response.content_part.added", "response.content_part.done"):
                        part = event.get("part")
                        if isinstance(part, dict) and part.get("type") == "refusal":
                            output_problem = "refusal"
                        elif not isinstance(part, dict) or part.get("type") not in ("output_text", "reasoning_text"):
                            output_problem = "unexpected_output"
                    if kind == "response.failed":
                        diagnostic = _response_diagnostic({"error": result.get("error")}, operation="inference")
                        raise _service_failure(result.get("error"), diagnostic={**stream_diagnostic, **diagnostic})
                    if kind == "error":
                        diagnostic = _response_diagnostic({"error": event}, operation="inference")
                        raise _service_failure(event, diagnostic={**stream_diagnostic, **diagnostic})
                    if kind == "response.incomplete":
                        raise InvalidResponse("incomplete")
                    if kind != "response.completed":
                        continue
                    if not isinstance(result, dict):
                        raise InvalidResponse("unexpected_shape")
                    if result.get("status") != "completed":
                        raise InvalidResponse("noncompleted_status")
                    if result.get("model") != MODEL:
                        raise CloudUnavailable("model")
                    if output_problem is not None:
                        raise InvalidResponse(output_problem)
                    output = result.get("output", [])
                    if (not isinstance(output, list) or any(
                            not isinstance(item, dict) or item.get("type") == "message"
                            and not isinstance(item.get("content"), list) for item in output)):
                        raise InvalidResponse("unexpected_shape")
                    if any(item.get("type") not in ("message", "reasoning") for item in output):
                        raise InvalidResponse("unexpected_output")
                    for item in output:
                        if item.get("type") != "message":
                            continue
                        for part in item["content"]:
                            if isinstance(part, dict) and part.get("type") == "refusal":
                                raise InvalidResponse("refusal")
                            if (not isinstance(part, dict) or part.get("type") != "output_text"
                                    or not isinstance(part.get("text"), str)):
                                raise InvalidResponse("unexpected_shape")
                    texts = [part["text"] for item in output
                             if isinstance(item, dict) and item.get("type") == "message"
                             for part in item.get("content", [])
                             if isinstance(part, dict) and part.get("type") == "output_text"
                             and isinstance(part.get("text"), str)]
                    streamed_texts = []
                    for _, part in sorted(streamed.items()):
                        delta_text = "".join(part["deltas"])
                        if (part["done"] is not None and part["deltas"]
                                and part["done"] != delta_text):
                            raise InvalidResponse("unexpected_shape")
                        streamed_texts.append(part["done"] if part["done"] is not None else delta_text)
                    if any(texts) and any(streamed_texts) and "".join(texts) != "".join(streamed_texts):
                        raise InvalidResponse("unexpected_shape")
                    if not texts or not any(texts):
                        texts = streamed_texts
                    if not texts or not any(texts):
                        raise InvalidResponse("empty_output")
                    return "".join(texts)
        except CloudUnavailable as error:
            error.diagnostic = sanitize_diagnostic({**stream_diagnostic, **error.diagnostic})
            raise
        except (OSError, UnicodeError, TypeError, AttributeError) as error:
            raise CloudUnavailable("unknown_outcome", diagnostic={**stream_diagnostic,
                                   "exception_type": type(error).__name__}) from None
