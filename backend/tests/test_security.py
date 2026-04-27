"""Tests for backend.core.security — token issuance and verification."""

from __future__ import annotations

import time
import unittest
from uuid import uuid4

from backend.core import security as security_module
from backend.core.exceptions import UnauthorizedAppError
from backend.core.security import (
    MfaChallengeClaims,
    SessionClaims,
    create_mfa_challenge_token,
    create_session_token,
    generate_recovery_codes,
    hash_password,
    hash_recovery_code,
    normalize_recovery_code,
    seal_secret,
    unseal_secret,
    verify_mfa_challenge_token,
    verify_password,
    verify_session_token,
)


class TestSessionToken(unittest.TestCase):
    def _make_token(self, **overrides):
        defaults = {
            "user_id": uuid4(),
            "organization_id": uuid4(),
            "email": "test@example.com",
            "session_id": uuid4(),
            "expires_at_epoch": int(time.time()) + 3600,
        }
        defaults.update(overrides)
        return create_session_token(**defaults), defaults

    def test_roundtrip(self):
        token, params = self._make_token()
        claims = verify_session_token(token)
        self.assertIsInstance(claims, SessionClaims)
        self.assertEqual(claims.user_id, params["user_id"])
        self.assertEqual(claims.organization_id, params["organization_id"])
        self.assertEqual(claims.email, "test@example.com")
        self.assertEqual(claims.session_id, params["session_id"])

    def test_expired_raises(self):
        token, _ = self._make_token(expires_at_epoch=int(time.time()) - 1)
        with self.assertRaises(UnauthorizedAppError):
            verify_session_token(token)

    def test_tampered_signature_raises(self):
        token, _ = self._make_token()
        tampered = token[:-4] + "XXXX"
        with self.assertRaises(UnauthorizedAppError):
            verify_session_token(tampered)

    def test_wrong_type_raises(self):
        """An MFA challenge token must not be accepted as a session token."""
        user_id = uuid4()
        org_id = uuid4()
        mfa_token = create_mfa_challenge_token(
            user_id=user_id,
            organization_id=org_id,
            email="test@example.com",
            expires_at_epoch=int(time.time()) + 3600,
        )
        with self.assertRaises(UnauthorizedAppError):
            verify_session_token(mfa_token)

    def test_email_normalization(self):
        token, _ = self._make_token(email="  UPPER@Example.COM  ")
        claims = verify_session_token(token)
        self.assertEqual(claims.email, "upper@example.com")


class TestMfaChallengeToken(unittest.TestCase):
    def test_roundtrip(self):
        user_id = uuid4()
        org_id = uuid4()
        token = create_mfa_challenge_token(
            user_id=user_id,
            organization_id=org_id,
            email="mfa@test.com",
            expires_at_epoch=int(time.time()) + 600,
        )
        claims = verify_mfa_challenge_token(token)
        self.assertIsInstance(claims, MfaChallengeClaims)
        self.assertEqual(claims.user_id, user_id)

    def test_expired_raises(self):
        token = create_mfa_challenge_token(
            user_id=uuid4(),
            organization_id=uuid4(),
            email="x@x.com",
            expires_at_epoch=int(time.time()) - 1,
        )
        with self.assertRaises(UnauthorizedAppError):
            verify_mfa_challenge_token(token)


class TestPasswordHashing(unittest.TestCase):
    def test_hash_and_verify(self):
        pw = "super-secret-password"
        h = hash_password(pw)
        self.assertTrue(verify_password(pw, h))
        self.assertFalse(verify_password("wrong", h))

    def test_none_hash_returns_false(self):
        self.assertFalse(verify_password("any", None))

    def test_different_salts_produce_different_hashes(self):
        pw = "same-password"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        self.assertNotEqual(h1, h2)
        self.assertTrue(verify_password(pw, h1))
        self.assertTrue(verify_password(pw, h2))


class TestRecoveryCodes(unittest.TestCase):
    def test_generates_expected_count(self):
        codes = generate_recovery_codes(8)
        self.assertEqual(len(codes), 8)

    def test_codes_are_unique(self):
        codes = generate_recovery_codes(8)
        self.assertEqual(len(set(codes)), 8)

    def test_hash_and_normalize(self):
        code = "ABCD-1234"
        h = hash_recovery_code(code)
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 64)  # sha256 hex
        # Normalisation strips dashes
        self.assertEqual(normalize_recovery_code("ABCD-1234"), "ABCD1234")

    def test_hash_is_case_insensitive(self):
        self.assertEqual(hash_recovery_code("abcd-1234"), hash_recovery_code("ABCD-1234"))


class TestSecretSeal(unittest.TestCase):
    def test_seal_unseal_roundtrip(self):
        value = "my-totp-secret"
        sealed = seal_secret(value)
        self.assertNotEqual(sealed, value)
        recovered = unseal_secret(sealed)
        self.assertEqual(recovered, value)

    def test_unseal_none_returns_none(self):
        self.assertIsNone(unseal_secret(None))

    def test_tampered_raises(self):
        sealed = seal_secret("secret")
        with self.assertRaises(UnauthorizedAppError):
            unseal_secret(sealed[:-4] + "XXXX")

    def test_invalid_secret_raises(self):
        with self.assertRaises(UnauthorizedAppError):
            unseal_secret("not-a-valid-secret")

    def test_legacy_sealed_values_still_readable(self):
        value = "legacy-secret"
        nonce = b"\x01" * 16
        key = security_module._derive_secret_encryption_key()
        plaintext = value.encode("utf-8")
        keystream = security_module._derive_keystream(key, nonce, len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream, strict=False))
        mac = security_module.hmac.new(
            key,
            nonce + ciphertext,
            security_module.hashlib.sha256,
        ).digest()
        legacy = security_module._base64url_encode(nonce + ciphertext + mac)
        self.assertEqual(unseal_secret(legacy), value)

    def test_derived_key_is_cached(self):
        security_module._derive_secret_encryption_key.cache_clear()
        security_module._derive_secret_encryption_key()
        security_module._derive_secret_encryption_key()
        cache_info = security_module._derive_secret_encryption_key.cache_info()
        self.assertGreaterEqual(cache_info.hits, 1)


class TestProductionSecretGuard(unittest.TestCase):
    """Verify that the production secret guard in config fires correctly."""

    def test_weak_secret_rejected_in_production(self):
        import os
        from unittest.mock import patch

        # Clear the lru_cache so the new env is picked up
        from backend.core import config as config_module

        config_module.get_settings.cache_clear()
        env = {
            "ENVIRONMENT": "production",
            "SESSION_SECRET": "dev-session-secret",
            "DATABASE_URL": "postgresql+asyncpg://x:y@localhost/z",
        }
        try:
            with patch.dict(os.environ, env, clear=False), self.assertRaises(ValueError):
                config_module.Settings(_env_file=None)
        finally:
            config_module.get_settings.cache_clear()

    def test_strong_secret_accepted_in_production(self):
        import os
        from unittest.mock import patch

        from backend.core import config as config_module

        config_module.get_settings.cache_clear()
        env = {
            "ENVIRONMENT": "production",
            "SESSION_SECRET": "a" * 64,
            "DATABASE_URL": "postgresql+asyncpg://x:y@localhost/z",
        }
        try:
            with patch.dict(os.environ, env, clear=False):
                s = config_module.Settings(_env_file=None)
                self.assertEqual(s.app_env, "production")
        finally:
            config_module.get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
