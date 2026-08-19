from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from firebase_admin import auth
from flask import Request


class AuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    data: dict[str, Any]


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Falta una credencial Bearer válida.")
    return token


def require_user(request: Request) -> dict[str, Any]:
    try:
        return auth.verify_id_token(_bearer_token(request))
    except Exception as exc:
        raise AuthenticationError("Token de usuario inválido o vencido.") from exc


def require_device(request: Request, db: Any) -> DeviceIdentity:
    device_id = request.headers.get("X-Device-Id", "").strip()
    secret = _bearer_token(request)
    if not device_id:
        raise AuthenticationError("Falta el encabezado X-Device-Id.")

    snapshot = db.collection("devices").document(device_id).get()
    if not snapshot.exists:
        raise AuthenticationError("Dispositivo desconocido.")

    data = snapshot.to_dict() or {}
    supplied_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    expected_hash = str(data.get("deviceSecretHash", ""))
    if data.get("status") != "active" or not hmac.compare_digest(supplied_hash, expected_hash):
        raise AuthenticationError("Credencial de dispositivo inválida.")

    return DeviceIdentity(device_id=device_id, data=data)
