"""Regression test for backend/config.py's fail-fast JWT_SECRET_KEY check —
see docs/DECISIONS.md #28 for why this must raise at import time rather
than lazily on first use. validate_jwt_secret is its own function
specifically so it can be exercised directly here with different inputs,
without needing importlib.reload tricks to re-trigger module-level code.
"""
import pytest

from backend.config import PLACEHOLDER_JWT_SECRET_KEY, validate_jwt_secret


def test_validate_jwt_secret_rejects_none():
    with pytest.raises(RuntimeError):
        validate_jwt_secret(None)


def test_validate_jwt_secret_rejects_empty_string():
    with pytest.raises(RuntimeError):
        validate_jwt_secret("")


def test_validate_jwt_secret_rejects_committed_placeholder():
    with pytest.raises(RuntimeError):
        validate_jwt_secret(PLACEHOLDER_JWT_SECRET_KEY)


def test_validate_jwt_secret_accepts_a_real_looking_value():
    assert validate_jwt_secret("a-real-looking-secret-value") == "a-real-looking-secret-value"
