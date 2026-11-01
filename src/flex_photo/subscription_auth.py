"""Application-owned Sign in with ChatGPT; never discovers CLI credentials."""

from contextlib import contextmanager
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import stat
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import webbrowser

from .cloud_access import CloudUnavailable


ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
JWKS = ISSUER + "/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
APP_NAME = "Amazon Flex Photo Organizer"


class AuthenticationRejected(CloudUnavailable):
    """Only documented terminal refresh failures invalidate a renewable session."""

    def __init__(self, *, terminal=False):
        self.terminal = terminal
        super().__init__("authentication")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_json(url, fields=None):
    """Fixed official auth endpoints only, bounded reads, no credential redirects."""
    if url not in (TOKEN, JWKS):
        raise CloudUnavailable("authentication")
    request = Request(url, data=None if fields is None else urlencode(fields).encode(),
                      headers={"Accept": "application/json"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=30) as response:
            raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("Oversized authentication response")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Invalid authentication response")
        return result
    except HTTPError as error:
        try:
            body = json.loads(error.read(65536))
            code = body.get("error")
            if isinstance(code, dict):
                code = code.get("code")
        except (ValueError, AttributeError, UnicodeError, OSError):
            code = None
        finally:
            error.close()
        terminal = fields is not None and fields.get("grant_type") == "refresh_token" and code in (
            "invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
            "refresh_token_invalidated", "refresh_token_reused")
        raise AuthenticationRejected(terminal=terminal) from None
    except (URLError, TimeoutError, OSError):
        raise CloudUnavailable("network") from None
    except (ValueError, UnicodeError):
        raise CloudUnavailable("authentication") from None


def _dpapi(raw, *, decrypt=False):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise CloudUnavailable("authentication")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(target.data)


def _ordinary(path, *, directory=False):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise CloudUnavailable("authentication")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise CloudUnavailable("authentication")


class CredentialStore:
    """DPAPI at rest on Windows; private directory/files on Unix.

    The lock serializes sign-in and rotating-token refresh across app processes.
    Callers must hold locked() around load/update/save transactions.
    """

    def __init__(self, path=None):
        if path is None:
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) \
                if os.name == "nt" else Path.home() / ".config"
            path = base / "flex-photo" / "subscription.dat"
        self.path = Path(path)

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _ordinary(self.path.parent, directory=True)
        lock_path = self.path.with_suffix(".lock")
        if lock_path.exists() or lock_path.is_symlink():
            _ordinary(lock_path)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "r+b") as stream:
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise CloudUnavailable("authentication") from None
            try:
                if not stream.read(1):
                    stream.write(b"0")
                    stream.flush()
                yield self
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def load(self):
        if not self.path.exists() and not self.path.is_symlink():
            return {}
        _ordinary(self.path)
        try:
            raw = self.path.read_bytes()
            if os.name == "nt":
                raw = _dpapi(raw, decrypt=True)
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("Invalid credential record")
            return value
        except (OSError, ValueError, UnicodeError):
            raise CloudUnavailable("authentication") from None

    def save(self, record):
        raw = json.dumps(record, allow_nan=False).encode()
        if os.name == "nt":
            raw = _dpapi(raw)
        if self.path.exists() or self.path.is_symlink():
            _ordinary(self.path)
        descriptor, temporary = tempfile.mkstemp(prefix=".subscription-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if os.name != "nt":
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def validate_id_token(token, client_id, *, nonce=None, subject=None, fetch=http_json):
    """Verify published-key signature, issuer, audience, expiry, identity and nonce."""
    import jwt
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in ("RS256", "ES256") or not header.get("kid"):
            raise ValueError("Unsupported signing key")
        keys = fetch(JWKS)["keys"]
        if not isinstance(keys, list) or not all(isinstance(item, dict) for item in keys):
            raise ValueError("Invalid signing keys")
        matching = [item for item in keys if item.get("kid") == header["kid"]]
        if len(matching) != 1:
            raise ValueError("Unknown signing key")
        key = jwt.PyJWK.from_dict(matching[0], algorithm=header["alg"])
        claims = jwt.decode(token, key.key, algorithms=[header["alg"]],
                            audience=client_id, issuer=ISSUER,
                            options={"require": ["iss", "sub", "aud", "exp", "iat"]})
        if (not isinstance(claims["sub"], str) or not claims["sub"]
                or nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce)
                or subject is not None and claims["sub"] != subject):
            raise ValueError("Identity mismatch")
        return claims
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise CloudUnavailable("authentication") from None


def _token_record(result, previous, client_id, *, nonce=None, fetch=http_json):
    if (not isinstance(result, dict) or not isinstance(result.get("scope", ""), str)
            or not isinstance(result.get("token_type", ""), str)):
        raise CloudUnavailable("authentication")
    claims = validate_id_token(result.get("id_token", ""), client_id, nonce=nonce,
                               subject=previous.get("subject"), fetch=fetch)
    scopes = result.get("scope", " ".join(previous.get("scopes", []))).split()
    if (result.get("token_type", "").lower() != "bearer"
            or not all(isinstance(result.get(name), str) and result[name]
                       for name in ("access_token", "refresh_token"))
            or type(result.get("expires_in")) is not int or result["expires_in"] <= 0):
        raise CloudUnavailable("authentication")
    record = {"client_id": client_id, "ext_agent_host_id": previous["ext_agent_host_id"],
            "subject": claims["sub"], "email": claims.get("email"), "scopes": scopes,
            "access_token": result["access_token"], "refresh_token": result["refresh_token"],
            "id_token": result["id_token"], "expires_at": time.time() + result["expires_in"]}
    if (previous.get("client_id") == client_id and previous.get("subject") == claims["sub"]
            and _subscription_only_verified(previous)):
        record["subscription_only_confirmation"] = previous["subscription_only_confirmation"]
    return record


def access_token(store, *, fetch=http_json):
    """Read only this app's credential record; serialize rotating refreshes."""
    with store.locked():
        record = store.load()
        if ("chatgpt.tokens.use.direct" not in record.get("scopes", [])
                or not record.get("client_id") or not record.get("access_token")):
            raise CloudUnavailable("authentication")
        expiry = record.get("expires_at", 0)
        if type(expiry) not in (int, float) or not math.isfinite(expiry):
            raise CloudUnavailable("authentication")
        if expiry > time.time() + 60:
            return record["access_token"]
        try:
            result = fetch(TOKEN, {"grant_type": "refresh_token", "client_id": record["client_id"],
                                   "refresh_token": record.get("refresh_token", ""),
                                   "resource": RESOURCE})
        except AuthenticationRejected as error:
            if error.terminal:
                store.save({key: value for key, value in record.items()
                            if key not in ("access_token", "refresh_token", "id_token", "expires_at")})
            raise
        updated = _token_record(result, record, record["client_id"], fetch=fetch)
        store.save(updated)
        if "chatgpt.tokens.use.direct" not in updated["scopes"]:
            raise CloudUnavailable("authentication")
        return updated["access_token"]


def auth_status(store):
    """Local nonsecret status only; a grant is not subscription-only proof."""
    with store.locked():
        record = store.load()
    connected = bool(record.get("subject") and record.get("client_id")
                     and record.get("access_token") and record.get("refresh_token"))
    return {"connected": connected,
            "plan_usage_granted": connected and "chatgpt.tokens.use.direct" in record.get("scopes", []),
            "subscription_only_verified": connected and _subscription_only_verified(record)}


def _subscription_only_verified(record):
    marker = record.get("subscription_only_confirmation")
    return (isinstance(marker, dict)
            and marker == {"client_id": record.get("client_id"), "subject": record.get("subject"),
                           "policy": "subscription-only",
                           "source": "user-verified-provider-configuration"}
            and bool(record.get("client_id") and record.get("subject"))
            and "chatgpt.tokens.use.direct" in record.get("scopes", []))


def confirm_subscription_only(store):
    """Record the user's verified provider configuration for this connection.

    This is user verification, not a server attestation. Never enable a separate
    API key, credit purchase or alternative request path.
    """
    with store.locked():
        record = store.load()
        if (not all(record.get(key) for key in ("client_id", "subject", "access_token", "refresh_token"))
                or "chatgpt.tokens.use.direct" not in record.get("scopes", [])):
            raise CloudUnavailable("authentication")
        record["subscription_only_confirmation"] = {
            "client_id": record["client_id"], "subject": record["subject"],
            "policy": "subscription-only", "source": "user-verified-provider-configuration"}
        store.save(record)


class SubscriptionOnlyGuard:
    """Read-only check of the protected, connection-bound user confirmation."""

    def __init__(self, store):
        self.store = store

    def check_available(self):
        with self.store.locked():
            record = self.store.load()
        if not _subscription_only_verified(record):
            raise CloudUnavailable("included_only_unverified")


def sign_in(store, *, open_browser=webbrowser.open, fetch=http_json, timeout=180):
    """Explicit interactive app-owned authorization; does not enable inference."""
    with store.locked():
        record = store.load()
        if "ext_agent_host_id" not in record:
            record["ext_agent_host_id"] = "urn:uuid:" + str(uuid.uuid4())
            store.save(record)
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        callback = {}

        class Handler(BaseHTTPRequestHandler):
            def end_headers(self):
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

            def do_GET(self):
                parsed = urlsplit(self.path)
                values = parse_qs(parsed.query, keep_blank_values=True)
                if (parsed.path != "/auth/callback" or any(len(v) != 1 for v in values.values())
                        or not secrets.compare_digest(values.get("state", [""])[0], state)):
                    self.send_error(400)
                    return
                callback.update({key: value[0] for key, value in values.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<!doctype html><meta charset='utf-8'>"
                                 b"<script>history.replaceState(null,'','/auth/done')</script>"
                                 b"<title>Authorization received</title>"
                                 b"Authorization received. Return to the application.")

            def log_message(self, *_):
                pass  # Callback URLs contain private authorization material.

        class CallbackServer(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(1)
                return connection, address

            def handle_error(self, request, client_address):
                pass  # Never print callback fragments or authorization material.

        with CallbackServer(("127.0.0.1", 0), Handler) as server:
            redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
            parameters = {"client_id": record.get("client_id", "dynamic_agent_client"),
                          "ext_agent_host_id": record["ext_agent_host_id"], "response_type": "code",
                          "redirect_uri": redirect, "scope": SCOPES, "resource": RESOURCE,
                          "state": state, "nonce": nonce, "code_challenge_method": "S256",
                          "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()}
            if not record.get("client_id"):
                parameters["agent_name_hint"] = APP_NAME
            # No ID token in browser URLs; ordinary account selection is supported.
            if not open_browser(AUTHORIZE + "?" + urlencode(parameters)):
                raise CloudUnavailable("authentication")
            deadline = time.monotonic() + timeout
            server.timeout = 1
            while not callback and time.monotonic() < deadline:
                server.handle_request()
        client = callback.get("client_id", record.get("client_id"))
        if (callback.get("error") or not callback.get("code") or not client
                or client == "dynamic_agent_client"
                or record.get("client_id") and client != record["client_id"]):
            raise CloudUnavailable("authentication")
        if not record.get("client_id"):
            record["client_id"] = client
            store.save(record)
        result = fetch(TOKEN, {"grant_type": "authorization_code", "client_id": client,
                               "code": callback["code"], "code_verifier": verifier,
                               "redirect_uri": redirect, "resource": RESOURCE})
        updated = _token_record(result, record, client, nonce=nonce, fetch=fetch)
        store.save(updated)
        return "chatgpt.tokens.use.direct" in updated["scopes"]
