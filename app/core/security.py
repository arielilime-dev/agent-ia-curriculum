"""Password hashing, password policy and JWT access tokens.

Design notes
------------
* Passwords are stored with PBKDF2-HMAC-SHA256 (>= 600k iterations in
  production, OWASP 2023) using a per-password random salt and an
  algorithm-tagged, self-describing format::

      pbkdf2_sha256$600000$<salt_b64>$<digest_b64>

  The tag and iteration count allow transparent upgrades via
  :func:`password_needs_rehash`.
* Access tokens are compact HS256 JWTs implemented with the standard library
  only, so there is no algorithm-confusion surface (``alg`` is allow-listed).
* Refresh tokens are opaque (``secrets.token_urlsafe``) and only their SHA-256
  digest is persisted, so a database leak cannot be replayed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings

# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------

MAX_PASSWORD_LENGTH = 128
PASSWORD_ALGORITHM = "pbkdf2_sha256"

# A small blocklist that catches obviously weak choices without pretending to
# be a full dictionary. Real deployments should plug a breached-password API.
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "12345678",
        "123456789",
        "1234567890",
        "password",
        "password1",
        "password123",
        "senha123",
        "senha1234",
        "qwerty123",
        "abc12345",
        "admin123",
        "letmein1",
        "iloveyou",
        "welcome1",
        "mudar123",
        "trocar123",
        "recruta123",
        "curriculo123",
    }
)


class WeakPasswordError(ValueError):
    """Raised when a password does not satisfy the configured policy."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def password_policy_errors(password: str, *, min_length: int = 8) -> list[str]:
    """Return a list of human-readable policy violations (empty when valid)."""
    problems: list[str] = []
    if not isinstance(password, str) or not password:
        return ["Password is required"]
    if len(password) < min_length:
        problems.append(f"Password must be at least {min_length} characters long")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long")
    if password.strip() != password or not password.strip():
        problems.append("Password must not start or end with whitespace")
    if not any(char.islower() for char in password):
        problems.append("Password must contain a lowercase letter")
    if not any(char.isupper() for char in password):
        problems.append("Password must contain an uppercase letter")
    if not any(char.isdigit() for char in password):
        problems.append("Password must contain a digit")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("Password is too common")
    if len(set(password)) == 1:
        problems.append("Password must contain a variety of characters")
    return problems


def validate_password_strength(password: str, *, min_length: int = 8) -> None:
    """Raise :class:`WeakPasswordError` when *password* violates the policy."""
    problems = password_policy_errors(password, min_length=min_length)
    if problems:
        raise WeakPasswordError(problems)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _pbkdf2(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)


def hash_password(password: str, *, iterations: int = 600_000, salt: bytes | None = None) -> str:
    """Hash *password* with a fresh (or provided) salt."""
    if not password:
        raise ValueError("password must not be empty")
    if iterations < 1:
        raise ValueError("iterations must be positive")
    salt = salt or secrets.token_bytes(16)
    digest = _pbkdf2(password, salt, iterations)
    return f"{PASSWORD_ALGORITHM}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification. Malformed hashes fail closed."""
    if not isinstance(password, str) or not password or not isinstance(stored_hash, str):
        return False
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        if iterations <= 0 or iterations > 5_000_000:
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
    except (ValueError, binascii.Error, UnicodeError):
        return False
    if not salt or not expected:
        return False
    actual = _pbkdf2(password, salt, iterations)
    return hmac.compare_digest(actual, expected)


def password_needs_rehash(stored_hash: str, *, iterations: int) -> bool:
    """Return ``True`` when *stored_hash* uses weaker parameters than configured."""
    try:
        algorithm, iterations_raw, _, _ = stored_hash.split("$", 3)
    except (ValueError, AttributeError):
        return True
    return algorithm != PASSWORD_ALGORITHM or int(iterations_raw) < iterations


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


class TokenError(Exception):
    """Base class for token validation failures."""


class InvalidTokenError(TokenError):
    """The token is malformed, forged or carries invalid claims."""


class ExpiredTokenError(TokenError):
    """The token is well formed but outside its validity window."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise InvalidTokenError("Malformed token segment")
    if any(
        char not in "-_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        for char in value
    ):
        raise InvalidTokenError("Malformed token segment")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (binascii.Error, ValueError) as exc:
        raise InvalidTokenError("Malformed token segment") from exc


def _json_encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign(message: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()


def create_access_token(
    subject: str,
    settings: Settings,
    *,
    now: datetime | None = None,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed HS256 access token for *subject* (the user id)."""
    if not subject:
        raise ValueError("subject must not be empty")
    issued_at = now or datetime.now(UTC)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)
    ttl = expires_delta or timedelta(minutes=settings.access_token_ttl_minutes)
    expires_at = issued_at + ttl
    payload: dict[str, Any] = {
        "sub": subject,
        "iss": settings.jwt_issuer,
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        # Never allow caller-supplied claims to override security claims.
        for key, value in extra_claims.items():
            payload.setdefault(key, value)
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    signing_input = (
        f"{_b64url_encode(_json_encode(header))}.{_b64url_encode(_json_encode(payload))}"
    )
    signature = _b64url_encode(_sign(signing_input.encode("ascii"), settings.jwt_secret_key))
    return f"{signing_input}.{signature}"


def decode_access_token(
    token: str,
    settings: Settings,
    *,
    now: datetime | None = None,
    leeway_seconds: int = 0,
    verify_expiry: bool = True,
) -> dict[str, Any]:
    """Validate *token* and return its claims.

    Raises :class:`ExpiredTokenError` or :class:`InvalidTokenError`; the
    original token is never included in error messages.
    """
    if not isinstance(token, str) or token.count(".") != 2:
        raise InvalidTokenError("Malformed token")
    header_raw, payload_raw, signature_raw = token.split(".")

    try:
        header = json.loads(_b64url_decode(header_raw))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidTokenError("Malformed token header") from exc
    if not isinstance(header, dict) or header.get("alg") != JWT_ALGORITHM:
        raise InvalidTokenError("Unsupported token algorithm")
    if header.get("typ", "JWT") != "JWT":
        raise InvalidTokenError("Unsupported token type")

    expected_signature = _sign(
        f"{header_raw}.{payload_raw}".encode("ascii"), settings.jwt_secret_key
    )
    try:
        provided_signature = _b64url_decode(signature_raw)
    except InvalidTokenError:
        raise
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise InvalidTokenError("Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_raw))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidTokenError("Malformed token payload") from exc
    if not isinstance(payload, dict):
        raise InvalidTokenError("Malformed token payload")

    if payload.get("iss") != settings.jwt_issuer:
        raise InvalidTokenError("Invalid token issuer")
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("Invalid token type")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidTokenError("Invalid token subject")

    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    reference_ts = reference.timestamp()
    exp = payload.get("exp")
    iat = payload.get("iat")
    if verify_expiry:
        if not isinstance(exp, int):
            raise InvalidTokenError("Missing token expiry")
        if reference_ts > exp + leeway_seconds:
            raise ExpiredTokenError("Token has expired")
        if isinstance(iat, int) and iat > reference_ts + leeway_seconds:
            raise InvalidTokenError("Token issued in the future")
    return payload


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------

REFRESH_TOKEN_BYTES = 48


def generate_refresh_token() -> str:
    """Generate a high-entropy opaque refresh token."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """Return the hex SHA-256 digest stored for a refresh token."""
    if not token:
        raise ValueError("token must not be empty")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
