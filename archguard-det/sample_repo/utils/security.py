"""Cryptographic hashing, token utilities, and route authentication decorator."""

import functools
import hashlib
import hmac
import secrets
import time
from flask import jsonify, request


_TOKEN_SECRET = "baseline-token-secret"


def hash_password(password: str, salt: str = "") -> str:
    """Hash a plaintext password deterministically with SHA-256."""
    effective_salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256(f"{effective_salt}:{password}".encode("utf-8")).hexdigest()
    return f"{effective_salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against its salted SHA-256 digest."""
    if "$" not in stored_hash:
        return False
    salt, expected = stored_hash.split("$", 1)
    candidate = hash_password(password, salt=salt).split("$", 1)[1]
    return hmac.compare_digest(candidate, expected)


def generate_token(user_id: int, role: str = "customer") -> str:
    """Create a signed session token for an authenticated user."""
    issued_at = int(time.time())
    payload = f"{user_id}:{role}:{issued_at}"
    signature = hmac.new(
        _TOKEN_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{signature}"


def decode_token(token: str) -> dict | None:
    """Verify and decode a signed session token."""
    parts = token.split(":")
    if len(parts) != 4:
        return None
    user_id_str, role, issued_str, signature = parts
    payload = f"{user_id_str}:{role}:{issued_str}"
    expected_sig = hmac.new(
        _TOKEN_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        return None
    return {"user_id": int(user_id_str), "role": role, "issued_at": int(issued_str)}


def require_auth(fn):
    """Decorator enforcing Bearer authentication on protected route handlers."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing Bearer token"}), 401
        token = auth_header[len("Bearer "):].strip()
        claims = decode_token(token)
        if claims is None:
            return jsonify({"error": "Invalid authentication token"}), 401
        request.user_claims = claims
        return fn(*args, **kwargs)

    return wrapper
