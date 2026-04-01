from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from dataclasses import dataclass
from uuid import UUID

from backend.core.config import settings
from backend.core.exceptions import UnauthorizedAppError

PBKDF2_ITERATIONS = 600_000
HASH_NAME = "sha256"
TOTP_INTERVAL_SECONDS = 30
TOTP_DIGITS = 6
RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_LENGTH = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(HASH_NAME, password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_{HASH_NAME}${PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False

    try:
        algorithm, iterations_text, salt_b64, digest_b64 = password_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != f"pbkdf2_{HASH_NAME}":
        return False

    try:
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64)
        expected_digest = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False

    candidate_digest = hashlib.pbkdf2_hmac(
        HASH_NAME,
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate_digest, expected_digest)


@dataclass(slots=True)
class SessionClaims:
    session_id: UUID
    user_id: UUID
    organization_id: UUID
    email: str
    expires_at_epoch: int


@dataclass(slots=True)
class MfaChallengeClaims:
    user_id: UUID
    organization_id: UUID
    email: str
    expires_at_epoch: int


def create_session_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    email: str,
    session_id: UUID,
    expires_at_epoch: int,
) -> str:
    return _create_signed_token(
        {
            "typ": "session",
            "sid": str(session_id),
            "sub": str(user_id),
            "org": str(organization_id),
            "email": email.strip().lower(),
            "exp": expires_at_epoch,
            "iat": int(time.time()),
        }
    )


def verify_session_token(token: str) -> SessionClaims:
    payload = _verify_signed_token(token, expected_type="session")
    try:
        session_id = UUID(str(payload["sid"]))
        user_id = UUID(str(payload["sub"]))
        organization_id = UUID(str(payload["org"]))
        email = str(payload["email"]).strip().lower()
        expires_at_epoch = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedAppError("Authentication is required.") from exc

    return SessionClaims(
        session_id=session_id,
        user_id=user_id,
        organization_id=organization_id,
        email=email,
        expires_at_epoch=expires_at_epoch,
    )


def create_mfa_challenge_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    email: str,
    expires_at_epoch: int,
) -> str:
    return _create_signed_token(
        {
            "typ": "mfa_challenge",
            "sub": str(user_id),
            "org": str(organization_id),
            "email": email.strip().lower(),
            "exp": expires_at_epoch,
            "iat": int(time.time()),
        }
    )


def verify_mfa_challenge_token(token: str) -> MfaChallengeClaims:
    payload = _verify_signed_token(token, expected_type="mfa_challenge")
    try:
        user_id = UUID(str(payload["sub"]))
        organization_id = UUID(str(payload["org"]))
        email = str(payload["email"]).strip().lower()
        expires_at_epoch = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedAppError("The MFA challenge is invalid or has expired.") from exc

    return MfaChallengeClaims(
        user_id=user_id,
        organization_id=organization_id,
        email=email,
        expires_at_epoch=expires_at_epoch,
    )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_token_prefix(token: str, length: int = 16) -> str:
    return token[:max(8, length)]


def create_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def build_totp_uri(*, secret: str, email: str, issuer: str) -> str:
    label = f"{issuer}:{email.strip().lower()}"
    return f"otpauth://totp/{_quote_uri_component(label)}?secret={secret}&issuer={_quote_uri_component(issuer)}"


def verify_totp_code(code: str, secret: str, *, now_epoch: int | None = None, window: int = 1) -> bool:
    normalized_code = "".join(ch for ch in code if ch.isdigit())
    if len(normalized_code) != TOTP_DIGITS:
        return False

    key = _decode_base32_secret(secret)
    if not key:
        return False

    current_time = int(time.time() if now_epoch is None else now_epoch)
    current_counter = current_time // TOTP_INTERVAL_SECONDS
    for offset in range(-window, window + 1):
        expected = _generate_totp_code(key, current_counter + offset)
        if hmac.compare_digest(normalized_code, expected):
            return True
    return False


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    codes: list[str] = []
    while len(codes) < max(1, count):
        raw = secrets.token_hex(4).upper()
        formatted = f"{raw[:4]}-{raw[4:]}"
        if formatted not in codes:
            codes.append(formatted)
    return codes


def hash_recovery_code(code: str) -> str:
    normalized = normalize_recovery_code(code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def seal_secret(value: str) -> str:
    plaintext = value.encode("utf-8")
    nonce = secrets.token_bytes(16)
    key = _derive_secret_encryption_key()
    keystream = _derive_keystream(key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream, strict=False))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return _base64url_encode(nonce + ciphertext + mac)


def unseal_secret(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        raw = _base64url_decode(value)
    except (ValueError, TypeError):
        raise UnauthorizedAppError("Stored secret material is invalid.")
    if len(raw) < 16 + 32:
        raise UnauthorizedAppError("Stored secret material is invalid.")
    nonce = raw[:16]
    ciphertext = raw[16:-32]
    provided_mac = raw[-32:]
    key = _derive_secret_encryption_key()
    expected_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(provided_mac, expected_mac):
        raise UnauthorizedAppError("Stored secret material is invalid.")
    keystream = _derive_keystream(key, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream, strict=False))
    return plaintext.decode("utf-8")


def _create_signed_token(payload: dict[str, object]) -> str:
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _sign_value(encoded_payload)
    return f"{encoded_payload}.{signature}"


def _verify_signed_token(token: str, *, expected_type: str) -> dict[str, object]:
    try:
        encoded_payload, provided_signature = token.split(".", 1)
    except ValueError as exc:
        raise UnauthorizedAppError("Authentication is required.") from exc

    expected_signature = _sign_value(encoded_payload)
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise UnauthorizedAppError("Authentication is required.")

    try:
        payload = json.loads(_base64url_decode(encoded_payload).decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UnauthorizedAppError("Authentication is required.") from exc

    if payload.get("typ") != expected_type:
        raise UnauthorizedAppError("Authentication is required.")

    expires_at_epoch = int(payload.get("exp", 0))
    if expires_at_epoch <= int(time.time()):
        if expected_type == "mfa_challenge":
            raise UnauthorizedAppError("The MFA challenge has expired. Sign in again.")
        raise UnauthorizedAppError("Your session has expired. Sign in again.")
    return payload


def _derive_secret_encryption_key() -> bytes:
    return hashlib.pbkdf2_hmac(
        HASH_NAME,
        settings.session_secret.encode("utf-8"),
        b"neuromarketer-secret-seal",
        200_000,
        dklen=32,
    )


def _derive_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        block = hmac.new(key, nonce + struct.pack(">I", counter), hashlib.sha256).digest()
        output.extend(block)
        counter += 1
    return bytes(output[:length])


def _generate_totp_code(secret: bytes, counter: int) -> str:
    message = counter.to_bytes(8, "big", signed=False)
    digest = hmac.new(secret, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = digest[offset : offset + 4]
    code_int = int.from_bytes(truncated, "big") & 0x7FFFFFFF
    return str(code_int % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def _decode_base32_secret(value: str) -> bytes:
    normalized = value.strip().replace(" ", "").upper()
    padding = "=" * (-len(normalized) % 8)
    return base64.b32decode(f"{normalized}{padding}", casefold=True)


def _quote_uri_component(value: str) -> str:
    safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"
    return "".join(character if character in safe else f"%{ord(character):02X}" for character in value)


def _sign_value(value: str) -> str:
    digest = hmac.new(
        settings.session_secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _base64url_encode(digest)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
