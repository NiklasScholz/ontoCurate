import jwt
import pytest

from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.core.security import (
    create_access_token,
    decode_token,
    get_password_hash,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = get_password_hash("correct-password")
    valid, _ = verify_password("correct-password", hashed)
    assert valid is True


def test_password_hash_rejects_wrong_password():
    hashed = get_password_hash("correct-password")
    valid, _ = verify_password("wrong-password", hashed)
    assert valid is False


def test_access_token_roundtrip():
    token = create_access_token(subject="someone@example.com")
    payload = decode_token(token)
    assert payload["sub"] == "someone@example.com"


def test_decode_token_rejects_tampered_token():
    token = create_access_token(subject="someone@example.com") + "oqioqeioqejo"
    with pytest.raises(UnauthorizedException):
        decode_token(token)


def test_decode_token_rejects_expired_token():
    expired = jwt.encode(
        {"sub": "someone@example.com", "exp": 0},
        settings.secret_key,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedException):
        decode_token(expired)
