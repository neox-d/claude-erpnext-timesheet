import pytest
from scripts.crypto import encrypt_password, decrypt_password


def test_roundtrip():
    """encrypt then decrypt returns the original password."""
    assert decrypt_password(encrypt_password("my_secret")) == "my_secret"


def test_encrypted_value_has_enc_prefix():
    assert encrypt_password("pass").startswith("enc:")


def test_plaintext_passthrough():
    """decrypt_password returns plaintext values unchanged (backward compat)."""
    assert decrypt_password("plaintext_password") == "plaintext_password"


def test_invalid_token_raises():
    """A malformed enc: token raises ValueError with a helpful message."""
    with pytest.raises(ValueError, match="decrypt"):
        decrypt_password("enc:notavalidtoken")


def test_different_passwords_produce_different_tokens():
    assert encrypt_password("password1") != encrypt_password("password2")


def test_same_password_produces_different_tokens():
    """Fernet uses random IV — same input yields different ciphertext each time."""
    assert encrypt_password("same") != encrypt_password("same")
