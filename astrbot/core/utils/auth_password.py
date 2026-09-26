"""Utilities for dashboard password hashing and verification."""

import hashlib
import hmac
import re
import secrets
import string

_PBKDF2_ITERATIONS = 600_000
_PBKDF2_SALT_BYTES = 16
_PBKDF2_ALGORITHM = "pbkdf2_sha256"
_PBKDF2_FORMAT = f"{_PBKDF2_ALGORITHM}$"
_DASHBOARD_PASSWORD_MIN_LENGTH = 8
_GENERATED_DASHBOARD_PASSWORD_LENGTH = 24
DEFAULT_DASHBOARD_PASSWORD = "astrbot"


def generate_dashboard_password() -> str:
    """Generate a strong dashboard password that satisfies the complexity policy."""
    alphabet = string.ascii_letters + string.digits
    password_chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        *(
            secrets.choice(alphabet)
            for _ in range(_GENERATED_DASHBOARD_PASSWORD_LENGTH - 3)
        ),
    ]
    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


def hash_dashboard_password(raw_password: str) -> str:
    """Return a salted hash for dashboard password using PBKDF2-HMAC-SHA256."""
    if not isinstance(raw_password, str) or raw_password == "":
        raise ValueError("Password cannot be empty")

    salt = secrets.token_hex(_PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    ).hex()
    return f"{_PBKDF2_FORMAT}{_PBKDF2_ITERATIONS}${salt}${digest}"


def validate_dashboard_password(raw_password: str) -> None:
    """Validate whether dashboard password meets the minimal complexity policy."""
    if not isinstance(raw_password, str) or raw_password == "":
        raise ValueError("Password cannot be empty")
    if len(raw_password) < _DASHBOARD_PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {_DASHBOARD_PASSWORD_MIN_LENGTH} characters long"
        )

    if not re.search(r"[A-Z]", raw_password):
        raise ValueError("Password must include at least one uppercase letter")
    if not re.search(r"[a-z]", raw_password):
        raise ValueError("Password must include at least one lowercase letter")
    if not re.search(r"\d", raw_password):
        raise ValueError("Password must include at least one digit")


def is_pbkdf2_dashboard_password(stored_hash: str) -> bool:
    """Return whether a stored value is a well-formed PBKDF2 password hash.

    Only the exact work factor this build generates is accepted. A stored hash
    with zero, negative, or unbounded iterations is treated as unusable rather
    than verified, so a corrupt configuration cannot stall login.
    """
    if not isinstance(stored_hash, str) or not stored_hash.startswith(_PBKDF2_FORMAT):
        return False
    parts = stored_hash.split("$")
    if len(parts) != 4:
        return False
    _, iterations_s, salt, digest = parts
    try:
        iterations = int(iterations_s)
        salt_bytes = bytes.fromhex(salt)
        digest_bytes = bytes.fromhex(digest)
    except ValueError:
        return False
    return (
        iterations == _PBKDF2_ITERATIONS
        and len(salt_bytes) == _PBKDF2_SALT_BYTES
        and len(digest_bytes) == hashlib.sha256().digest_size
    )


def verify_dashboard_password(stored_hash: str, candidate_password: str) -> bool:
    """Verify a candidate password against a stored PBKDF2-HMAC-SHA256 hash."""
    if not isinstance(stored_hash, str) or not isinstance(candidate_password, str):
        return False
    if not is_pbkdf2_dashboard_password(stored_hash):
        return False

    _, iterations_s, salt, digest = stored_hash.split("$")
    candidate_key = hashlib.pbkdf2_hmac(
        "sha256",
        candidate_password.encode("utf-8"),
        bytes.fromhex(salt),
        int(iterations_s),
    )
    return hmac.compare_digest(bytes.fromhex(digest), candidate_key)


def is_default_dashboard_password(stored_hash: str) -> bool:
    """Check whether the password still equals the built-in default value."""
    return verify_dashboard_password(stored_hash, DEFAULT_DASHBOARD_PASSWORD)
