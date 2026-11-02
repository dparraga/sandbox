"""App-owned OAuth checks; generated keys and loopback callbacks, no service calls."""

import json
import io
import os
import socket
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from flex_photo.cloud_access import CloudUnavailable
from flex_photo import subscription_auth as auth


class SubscriptionAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key()))
        cls.jwk.update(kid="test-key", alg="RS256", use="sig")

    def token(self, **changes):
        claims = {"iss": auth.ISSUER, "sub": "private-subject", "aud": "oaiapp_test",
                  "iat": int(time.time()), "exp": int(time.time()) + 3600,
                  "nonce": "test-nonce"}
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test-key"})

    def fetch_keys(self, url):
        self.assertEqual(url, auth.JWKS)
        return {"keys": [self.jwk]}

    def record(self, *, expired=False):
        return {"client_id": "oaiapp_test", "ext_agent_host_id": "urn:uuid:test",
                "subject": "private-subject", "scopes": ["chatgpt.tokens.use.direct"],
                "access_token": "private-access", "refresh_token": "private-refresh",
                "id_token": self.token(), "expires_at": 0 if expired else time.time() + 3600}

    def result(self, **changes):
        result = {"access_token": "next-access", "refresh_token": "next-refresh",
                  "id_token": self.token(), "token_type": "Bearer", "expires_in": 3600,
                  "scope": auth.SCOPES}
        result.update(changes)
        return result

    def test_signed_identity_claims_and_signature_are_verified(self):
        claims = auth.validate_id_token(self.token(), "oaiapp_test", nonce="test-nonce",
                                        fetch=self.fetch_keys)
        self.assertEqual(claims["sub"], "private-subject")
        for change in ({"iss": "https://other.invalid"}, {"aud": "other-client"},
                       {"exp": 1}, {"nonce": "other-nonce"}, {"sub": ""}):
            with self.subTest(change=change), self.assertRaises(CloudUnavailable):
                auth.validate_id_token(self.token(**change), "oaiapp_test", nonce="test-nonce",
                                       fetch=self.fetch_keys)
        bad = jwt.encode({"sub": "private-subject"}, "attacker" * 8, algorithm="HS256",
                         headers={"kid": "test-key"})
        with self.assertRaises(CloudUnavailable):
            auth.validate_id_token(bad, "oaiapp_test", fetch=self.fetch_keys)
        with self.assertRaises(CloudUnavailable):
            auth.validate_id_token(self.token().rsplit(".", 1)[0] + ".AAAA", "oaiapp_test",
                                   fetch=self.fetch_keys)
        for keys in (None, ["bad"], []):
            with self.subTest(keys=keys), self.assertRaises(CloudUnavailable):
                auth.validate_id_token(self.token(), "oaiapp_test", fetch=lambda _: {"keys": keys})

    def test_store_roundtrip_private_tokens_and_native_protection(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            record = self.record()
            with store.locked():
                store.save(record)
                self.assertEqual(store.load(), record)
                raw = store.path.read_bytes()
                if os.name == "nt":
                    self.assertNotIn(b"private-access", raw)
                    self.assertNotIn(b"private-refresh", raw)
                else:
                    self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(store.path.parent.stat().st_mode & 0o777, 0o700)
            with store.locked():
                self.assertEqual(store.load(), record)

    def test_second_process_style_store_lock_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            with store.locked(), self.assertRaises(CloudUnavailable):
                with auth.CredentialStore(store.path).locked():
                    self.fail("Concurrent refresh allowed")

    def test_valid_access_does_not_refresh_or_access_external_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            with store.locked():
                store.save(self.record())
            fetch = Mock(side_effect=AssertionError("Unexpected network"))
            self.assertEqual(auth.access_token(store, fetch=fetch), "private-access")
            fetch.assert_not_called()
            self.assertEqual(auth.auth_status(store), {"connected": True, "plan_usage_granted": True,
                                                       "subscription_only_verified": False})

    def test_refresh_rotates_atomically_and_reuses_issued_client(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            with store.locked():
                store.save(self.record(expired=True))
            calls = []

            def fetch(url, fields=None):
                calls.append((url, fields))
                return self.fetch_keys(url) if url == auth.JWKS else self.result()

            self.assertEqual(auth.access_token(store, fetch=fetch), "next-access")
            self.assertEqual(calls[0], (auth.TOKEN, {"grant_type": "refresh_token",
                             "client_id": "oaiapp_test", "refresh_token": "private-refresh",
                             "resource": auth.RESOURCE}))
            with store.locked():
                self.assertEqual(store.load()["refresh_token"], "next-refresh")

    def test_failed_refresh_preserves_credential_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            record = self.record(expired=True)
            with store.locked():
                store.save(record)
            for failure in (CloudUnavailable("network"), CloudUnavailable("authentication")):
                with self.assertRaises(CloudUnavailable):
                    auth.access_token(store, fetch=Mock(side_effect=failure))
                with store.locked():
                    self.assertEqual(store.load(), record)

    def test_terminal_refresh_failure_discards_only_invalid_tokens(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            with store.locked():
                store.save(self.record(expired=True))
            with self.assertRaises(CloudUnavailable):
                auth.access_token(store, fetch=Mock(side_effect=auth.AuthenticationRejected(terminal=True)))
            with store.locked():
                record = store.load()
            self.assertEqual(record["client_id"], "oaiapp_test")
            self.assertEqual(record["subject"], "private-subject")
            self.assertNotIn("access_token", record)
            self.assertNotIn("refresh_token", record)
            self.assertNotIn("id_token", record)

    def test_subscription_confirmation_is_protected_and_connection_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            with store.locked():
                store.save(self.record())
            guard = auth.SubscriptionOnlyGuard(store)
            with self.assertRaises(CloudUnavailable):
                guard.check_available()
            auth.confirm_subscription_only(store)
            guard.check_available()
            self.assertTrue(auth.auth_status(store)["subscription_only_verified"])
            with store.locked():
                confirmed = store.load()
            for key, value in (("client_id", "oaiapp_other"), ("subject", "other-subject"),
                               ("scopes", [])):
                changed = {**confirmed, key: value}
                with store.locked():
                    store.save(changed)
                with self.assertRaises(CloudUnavailable):
                    guard.check_available()
                self.assertFalse(auth.auth_status(store)["subscription_only_verified"])

    def test_confirmation_survives_only_same_verified_refresh_identity(self):
        record = self.record(expired=True)
        record["subscription_only_confirmation"] = {
            "client_id": record["client_id"], "subject": record["subject"],
            "policy": "subscription-only", "source": "user-verified-provider-configuration"}
        updated = auth._token_record(self.result(), record, record["client_id"], fetch=self.fetch_keys)
        self.assertEqual(updated["subscription_only_confirmation"], record["subscription_only_confirmation"])
        new_record = {key: value for key, value in record.items() if key != "subject"}
        updated = auth._token_record(self.result(), new_record, record["client_id"], fetch=self.fetch_keys)
        self.assertNotIn("subscription_only_confirmation", updated)

    def test_rotating_refresh_rejects_identity_change_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            record = self.record(expired=True)
            with store.locked():
                store.save(record)

            def fetch(url, fields=None):
                return self.fetch_keys(url) if url == auth.JWKS else self.result(id_token=self.token(sub="other"))

            with self.assertRaises(CloudUnavailable):
                auth.access_token(store, fetch=fetch)
            with store.locked():
                self.assertEqual(store.load(), record)

    def test_interactive_pkce_callback_and_verified_app_owned_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            captured = {}
            threads = []
            received = []

            def browser(url):
                self.assertTrue(url.startswith(auth.AUTHORIZE + "?"))
                captured.update({k: v[0] for k, v in parse_qs(urlsplit(url).query).items()})
                callback = captured["redirect_uri"] + "?" + urlencode({
                    "state": captured["state"], "code": "one-time-code", "client_id": "oaiapp_test"})
                def receive():
                    with urlopen(callback, timeout=5) as response:
                        received.append((dict(response.headers), response.read()))
                thread = threading.Thread(target=receive)
                thread.start()
                threads.append(thread)
                return True

            def fetch(url, fields=None):
                if url == auth.JWKS:
                    return self.fetch_keys(url)
                self.assertEqual(fields["redirect_uri"], captured["redirect_uri"])
                self.assertEqual(fields["client_id"], "oaiapp_test")
                challenge = auth.base64.urlsafe_b64encode(auth.hashlib.sha256(
                    fields["code_verifier"].encode()).digest()).rstrip(b"=").decode()
                self.assertEqual(challenge, captured["code_challenge"])
                return self.result(id_token=self.token(nonce=captured["nonce"]))

            self.assertTrue(auth.sign_in(store, open_browser=browser, fetch=fetch, timeout=5))
            for thread in threads:
                thread.join(5)
            self.assertEqual(len(received), 1)
            headers, page = received[0]
            self.assertEqual(headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertIn(b"history.replaceState(null,'','/auth/done')", page)
            self.assertNotIn(captured["state"].encode(), page)
            self.assertNotIn(b"one-time-code", page)
            self.assertEqual(captured["client_id"], "dynamic_agent_client")
            self.assertEqual(captured["agent_name_hint"], auth.APP_NAME)
            self.assertNotIn("id_token_hint", captured)
            self.assertEqual(captured["code_challenge_method"], "S256")
            with store.locked():
                self.assertEqual(store.load()["client_id"], "oaiapp_test")

    def test_timeout_does_not_exchange_code_and_host_survives(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            fetch = Mock()
            with self.assertRaises(CloudUnavailable):
                auth.sign_in(store, open_browser=lambda _: True, fetch=fetch, timeout=0)
            fetch.assert_not_called()
            with store.locked():
                self.assertTrue(store.load()["ext_agent_host_id"].startswith("urn:uuid:"))

    def test_partial_callback_connection_cannot_defeat_authorization_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = auth.CredentialStore(Path(temporary) / "private" / "subscription.dat")
            connections = []

            def browser(url):
                params = parse_qs(urlsplit(url).query)
                callback = urlsplit(params["redirect_uri"][0])
                connection = socket.create_connection((callback.hostname, callback.port), timeout=2)
                connection.sendall(b"GET /auth/callback")
                connections.append(connection)
                return True

            started = time.monotonic()
            try:
                with self.assertRaises(CloudUnavailable):
                    auth.sign_in(store, open_browser=browser, fetch=Mock(), timeout=0.1)
                self.assertLess(time.monotonic() - started, 3)
            finally:
                for connection in connections:
                    connection.close()

    def test_arbitrary_auth_endpoint_rejected_before_network(self):
        with self.assertRaises(CloudUnavailable):
            auth.http_json("https://other.invalid", {"refresh_token": "private"})

    def test_refresh_http_failure_keeps_only_safe_diagnostics_and_terminal_policy(self):
        body = io.BytesIO(b'{"error":"invalid_grant","error_description":"private credential text"}')
        error = HTTPError(auth.TOKEN, 400, "private reason", {"x-request-id": "req_" + "b" * 32}, body)
        with patch.object(auth, "build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(auth.AuthenticationRejected) as caught:
                auth.http_json(auth.TOKEN, {"grant_type": "refresh_token", "refresh_token": "private"})
        self.assertTrue(caught.exception.terminal)
        self.assertEqual(caught.exception.diagnostic, {"operation": "token_refresh", "http_status": 400,
            "service_code": "invalid_grant", "response_shape": "json_object", "request_id": "req_" + "b" * 32})
        self.assertNotIn("private", json.dumps(caught.exception.diagnostic))

    def test_signature_failure_diagnostic_has_safe_exception_type_only(self):
        with self.assertRaises(CloudUnavailable) as caught:
            auth.validate_id_token(self.token().rsplit(".", 1)[0] + ".AAAA", "oaiapp_test",
                                   fetch=self.fetch_keys)
        self.assertEqual(caught.exception.diagnostic, {"operation": "token_validation",
                         "exception_type": "InvalidSignatureError"})


if __name__ == "__main__":
    unittest.main()
