from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

PIN_HASH_ITERATIONS = 210_000


@dataclass(frozen=True)
class FactoryCredentials:
    device_id: str
    setup_pin: str
    device_secret: str
    setup_pin_salt: str
    setup_pin_hash: str
    device_secret_hash: str


def _pin_hash(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        salt,
        PIN_HASH_ITERATIONS,
    ).hex()


def create_factory_credentials(device_id: str) -> FactoryCredentials:
    setup_pin = f"{secrets.randbelow(100_000_000):08d}"
    device_secret = secrets.token_urlsafe(32)
    salt = secrets.token_bytes(16)
    return FactoryCredentials(
        device_id=device_id,
        setup_pin=setup_pin,
        device_secret=device_secret,
        setup_pin_salt=salt.hex(),
        setup_pin_hash=_pin_hash(setup_pin, salt),
        device_secret_hash=hashlib.sha256(device_secret.encode("utf-8")).hexdigest(),
    )


def verify_setup_pin(pin: str, salt_hex: str, expected_hash: str) -> bool:
    try:
        supplied_hash = _pin_hash(pin, bytes.fromhex(salt_hex))
    except ValueError:
        return False
    return hmac.compare_digest(supplied_hash, expected_hash)
