"""
Password encryption/decryption for timesheet config.

Uses Fernet symmetric encryption with a key derived from machine identity,
so the encrypted password is tied to the machine it was created on.

Encrypted values are prefixed with "enc:" to distinguish them from plaintext.
Plaintext values are accepted transparently for backward compatibility.
"""
import base64
import hashlib
import os
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    raise ImportError(
        "The 'cryptography' package is required. Install it with: pip install cryptography"
    )


def _derive_key() -> bytes:
    """Derive a Fernet-compatible key from machine identity and username."""
    machine_id = ""
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            machine_id = Path(path).read_text().strip()
            break
        except OSError:
            pass
    material = f"{machine_id}:{os.getenv('USER', 'user')}:erpnext-timesheet".encode()
    key_bytes = hashlib.pbkdf2_hmac("sha256", material, material, 100_000, dklen=32)
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_password(password: str) -> str:
    """Encrypt a plaintext password. Returns an 'enc:'-prefixed token."""
    token = Fernet(_derive_key()).encrypt(password.encode()).decode()
    return f"enc:{token}"


def decrypt_password(value: str) -> str:
    """
    Decrypt a password value from config.
    If the value starts with 'enc:', decrypts it.
    Otherwise returns it as-is (plaintext passthrough for compatibility).
    """
    if not value.startswith("enc:"):
        return value
    try:
        return Fernet(_derive_key()).decrypt(value[4:].encode()).decode()
    except InvalidToken:
        raise ValueError(
            "Failed to decrypt password. "
            "The config may have been created on a different machine. "
            "Re-run /timesheet to reconfigure."
        )
