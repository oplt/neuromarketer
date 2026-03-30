from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from uuid import UUID

from backend.core.config import settings
from backend.core.exceptions import UnauthorizedAppError

PBKDF2_ITERATIONS = 600_000
HASH_NAME = "sha256"


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
    user_id: UUID
    organization_id: UUID
    email: str
    expires_at_epoch: int


def create_session_token(*, user_id: UUID, organization_id: UUID, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "org": str(organization_id),
        "email": email,
        "exp": int(time.time()) + max(60, settings.session_ttl_minutes * 60),
    }
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _sign_value(encoded_payload)
    return f"{encoded_payload}.{signature}"


def verify_session_token(token: str) -> SessionClaims:
    try:
        encoded_payload, provided_signature = token.split(".", 1)
    except ValueError as exc:
        raise UnauthorizedAppError("Authentication is required.") from exc

    expected_signature = _sign_value(encoded_payload)
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise UnauthorizedAppError("Authentication is required.")

    try:
        payload = json.loads(_base64url_decode(encoded_payload).decode("utf-8"))
        user_id = UUID(str(payload["sub"]))
        organization_id = UUID(str(payload["org"]))
        email = str(payload["email"]).strip().lower()
        expires_at_epoch = int(payload["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UnauthorizedAppError("Authentication is required.") from exc

    if expires_at_epoch <= int(time.time()):
        raise UnauthorizedAppError("Your session has expired. Sign in again.")

    return SessionClaims(
        user_id=user_id,
        organization_id=organization_id,
        email=email,
        expires_at_epoch=expires_at_epoch,
    )


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
