from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask import Flask, jsonify, request
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import ValidationError

from .auth import AuthenticationError, require_device, require_user
from .config import settings
from .database import get_firestore_client
from .device_claim import verify_setup_pin
from .schemas import DeviceClaim, DeviceEvent, HomeSetup, ReadingBatch

app = Flask(__name__)


def _json_error(message: str, status: int, details: Any = None):
    body: dict[str, Any] = {"error": {"message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin and origin in settings.allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Device-Id"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.errorhandler(AuthenticationError)
def handle_authentication_error(error: AuthenticationError):
    return _json_error(str(error), 401)


@app.errorhandler(ValidationError)
def handle_validation_error(error: ValidationError):
    return _json_error("Solicitud inválida.", 422, error.errors(include_url=False))


@app.route("/health", methods=["GET"])
@app.route("/v1/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "smart-tanks-api"})


def _authenticated_user() -> tuple[dict[str, Any], str]:
    claims = require_user(request)
    user_id = str(claims.get("uid") or claims.get("sub") or "").strip()
    if not user_id:
        raise AuthenticationError("El token no contiene un usuario válido.")
    return claims, user_id


def _iso_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _tank_response(tank_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": tank_id,
        "name": data.get("name"),
        "shape": data.get("shape"),
        "heightCm": data.get("heightCm"),
        "diameterCm": data.get("diameterCm"),
        "capacityLiters": data.get("capacityLiters"),
        "lowLevelPercentage": data.get("lowLevelPercentage", 25),
        "status": data.get("status", "active"),
    }


def _device_response(device_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": device_id,
        "label": data.get("label", "SmartTank"),
        "status": data.get("status"),
        "firmwareVersion": data.get("firmwareVersion"),
        "channels": data.get("channels", []),
        "lastSeenAt": _iso_datetime(data.get("lastSeenAt")),
        "claimedAt": _iso_datetime(data.get("claimedAt")),
    }


def _home_member_role(db: Any, user_id: str, home_id: str) -> str | None:
    user_snapshot = db.collection("users").document(user_id).get()
    user_data = user_snapshot.to_dict() if user_snapshot.exists else {}
    if str((user_data or {}).get("activeHomeId", "")) != home_id:
        return None
    member_snapshot = (
        db.collection("homes")
        .document(home_id)
        .collection("members")
        .document(user_id)
        .get()
    )
    if not member_snapshot.exists:
        return None
    role = str((member_snapshot.to_dict() or {}).get("role", ""))
    return role if role in {"owner", "admin", "viewer"} else None


def _home_manager_role(db: Any, user_id: str, home_id: str) -> str | None:
    role = _home_member_role(db, user_id, home_id)
    return role if role in {"owner", "admin"} else None


@app.route("/v1/me/context", methods=["GET", "OPTIONS"])
def user_context():
    if request.method == "OPTIONS":
        return "", 204

    db = get_firestore_client()
    claims, user_id = _authenticated_user()
    user_snapshot = db.collection("users").document(user_id).get()
    user_data = user_snapshot.to_dict() if user_snapshot.exists else {}
    user_data = user_data or {}
    home_id = str(user_data.get("activeHomeId", "")).strip()
    user = {
        "id": user_id,
        "displayName": user_data.get("displayName") or claims.get("name"),
        "email": user_data.get("email") or claims.get("email"),
    }

    if not home_id:
        return jsonify({"user": user, "home": None, "tanks": []})

    home_ref = db.collection("homes").document(home_id)
    member_snapshot = home_ref.collection("members").document(user_id).get()
    if not member_snapshot.exists:
        return _json_error("El usuario no pertenece a la casa configurada.", 403)

    home_snapshot = home_ref.get()
    if not home_snapshot.exists:
        return _json_error("La casa configurada no existe.", 409)

    home_data = home_snapshot.to_dict() or {}
    tanks = [
        _tank_response(snapshot.id, snapshot.to_dict() or {})
        for snapshot in home_ref.collection("tanks").stream()
    ]
    tanks.sort(key=lambda tank: str(tank["id"]))
    return jsonify(
        {
            "user": user,
            "home": {
                "id": home_id,
                "name": home_data.get("name"),
                "timezone": home_data.get("timezone"),
                "role": (member_snapshot.to_dict() or {}).get("role"),
            },
            "tanks": tanks,
        }
    )


@app.route("/v1/homes", methods=["POST", "OPTIONS"])
def create_home():
    if request.method == "OPTIONS":
        return "", 204

    db = get_firestore_client()
    claims, user_id = _authenticated_user()
    payload = HomeSetup.model_validate(request.get_json(silent=False))
    user_ref = db.collection("users").document(user_id)
    user_snapshot = user_ref.get()
    existing_user = user_snapshot.to_dict() if user_snapshot.exists else {}
    existing_user = existing_user or {}
    if existing_user.get("activeHomeId"):
        return _json_error("El usuario ya tiene una casa activa.", 409)

    created_at = datetime.now(UTC)
    home_ref = db.collection("homes").document()
    member_ref = home_ref.collection("members").document(user_id)
    write_batch = db.batch()
    write_batch.set(
        home_ref,
        {
            "name": payload.name,
            "timezone": payload.timezone,
            "ownerUserId": user_id,
            "createdAt": created_at,
            "updatedAt": created_at,
        },
    )
    write_batch.set(
        member_ref,
        {"userId": user_id, "role": "owner", "createdAt": created_at},
    )
    write_batch.set(
        user_ref,
        {
            "displayName": payload.display_name or claims.get("name"),
            "email": claims.get("email"),
            "activeHomeId": home_ref.id,
            "createdAt": existing_user.get("createdAt", created_at),
            "updatedAt": created_at,
        },
        merge=True,
    )

    tanks: list[dict[str, Any]] = []
    for index, tank in enumerate(payload.tanks, start=1):
        tank_id = f"tank_{index}"
        tank_data = tank.model_dump(by_alias=True)
        tank_data.update(
            {
                "homeId": home_ref.id,
                "status": "active",
                "createdAt": created_at,
                "updatedAt": created_at,
            }
        )
        write_batch.set(home_ref.collection("tanks").document(tank_id), tank_data)
        tanks.append(_tank_response(tank_id, tank_data))

    write_batch.commit()
    return (
        jsonify(
            {
                "user": {
                    "id": user_id,
                    "displayName": payload.display_name or claims.get("name"),
                    "email": claims.get("email"),
                },
                "home": {
                    "id": home_ref.id,
                    "name": payload.name,
                    "timezone": payload.timezone,
                    "role": "owner",
                    "createdAt": _iso_datetime(created_at),
                },
                "tanks": tanks,
            }
        ),
        201,
    )


@app.route("/v1/homes/<home_id>/devices", methods=["GET", "OPTIONS"])
def list_devices(home_id: str):
    if request.method == "OPTIONS":
        return "", 204

    db = get_firestore_client()
    _, user_id = _authenticated_user()
    if not _home_member_role(db, user_id, home_id):
        return _json_error("El usuario no pertenece a esta casa.", 403)

    snapshots = db.collection("devices").where(
        filter=FieldFilter("homeId", "==", home_id)
    ).stream()
    devices = [
        _device_response(snapshot.id, snapshot.to_dict() or {})
        for snapshot in snapshots
    ]
    devices.sort(key=lambda device: str(device["id"]))
    return jsonify({"devices": devices})


@app.route("/v1/homes/<home_id>/devices/claim", methods=["POST", "OPTIONS"])
def claim_device(home_id: str):
    if request.method == "OPTIONS":
        return "", 204

    db = get_firestore_client()
    _, user_id = _authenticated_user()
    if not _home_manager_role(db, user_id, home_id):
        return _json_error("Solo un propietario o administrador puede asociar SmartTanks.", 403)

    payload = DeviceClaim.model_validate(request.get_json(silent=False))
    device_ref = db.collection("devices").document(payload.device_id)
    device_snapshot = device_ref.get()
    if not device_snapshot.exists:
        return _json_error("El ID o el PIN del SmartTank son incorrectos.", 403)

    device_data = device_snapshot.to_dict() or {}
    if device_data.get("status") != "unclaimed":
        return _json_error("Este SmartTank ya está asociado o no está disponible.", 409)

    now = datetime.now(UTC)
    attempts = int(device_data.get("claimAttempts", 0))
    if attempts >= 5:
        return _json_error("El SmartTank está bloqueado por demasiados intentos.", 429)
    if not verify_setup_pin(
        payload.setup_pin,
        str(device_data.get("setupPinSalt", "")),
        str(device_data.get("setupPinHash", "")),
    ):
        device_ref.update(
            {"claimAttempts": attempts + 1, "lastClaimAttemptAt": now, "updatedAt": now}
        )
        return _json_error("El ID o el PIN del SmartTank son incorrectos.", 403)

    tank_snapshots = list(
        db.collection("homes").document(home_id).collection("tanks").stream()
    )
    tank_snapshots.sort(key=lambda snapshot: snapshot.id)
    if not tank_snapshots:
        return _json_error("La casa no tiene tanques configurados.", 409)
    channels = [
        {"channel": chr(ord("A") + index), "tankId": snapshot.id}
        for index, snapshot in enumerate(tank_snapshots[:2])
    ]

    update = {
        "homeId": home_id,
        "label": payload.label,
        "status": "active",
        "channels": channels,
        "sampleIntervalSeconds": 30,
        "configVersion": 1,
        "claimedAt": now,
        "claimedByUserId": user_id,
        "claimAttempts": 0,
        "updatedAt": now,
    }
    audit_ref = db.collection("auditLogs").document()
    write_batch = db.batch()
    write_batch.set(device_ref, update, merge=True)
    write_batch.create(
        audit_ref,
        {
            "action": "device_claimed",
            "deviceId": payload.device_id,
            "homeId": home_id,
            "actorUserId": user_id,
            "createdAt": now,
        },
    )
    write_batch.commit()
    device_data.update(update)
    return jsonify({"device": _device_response(payload.device_id, device_data)})


@app.route("/v1/device/readings/batch", methods=["POST", "OPTIONS"])
def ingest_readings():
    if request.method == "OPTIONS":
        return "", 204

    db = get_firestore_client()
    identity = require_device(request, db)
    payload = ReadingBatch.model_validate(request.get_json(silent=False))
    if payload.device_id != identity.device_id:
        return _json_error("deviceId no coincide con la credencial.", 403)
    if len(payload.readings) > settings.max_batch_size:
        return _json_error("El lote excede el máximo permitido.", 422)

    home_id = str(identity.data.get("homeId", "")).strip()
    if not home_id:
        return _json_error("El dispositivo no está asignado a una casa.", 409)

    channel_map = {
        str(channel["channel"]): str(channel["tankId"])
        for channel in identity.data.get("channels", [])
        if "channel" in channel and "tankId" in channel
    }
    invalid_channels = sorted({item.tank_channel for item in payload.readings if item.tank_channel not in channel_map})
    if invalid_channels:
        return _json_error("El dispositivo intentó publicar canales no asignados.", 403, invalid_channels)

    received_at = datetime.now(UTC)
    refs = [
        db.collection("readings").document(
            f"{identity.device_id}:{item.sequence}:{item.tank_channel}"
        )
        for item in payload.readings
    ]
    existing_ids = {snapshot.id for snapshot in db.get_all(refs) if snapshot.exists}
    write_batch = db.batch()
    accepted: list[dict[str, Any]] = []
    latest_by_tank: dict[str, tuple[int, dict[str, Any]]] = {}

    for item, document_ref in zip(payload.readings, refs, strict=True):
        status = "duplicate" if document_ref.id in existing_ids else "created"
        accepted.append(
            {"sequence": item.sequence, "tankChannel": item.tank_channel, "status": status}
        )
        if status == "duplicate":
            continue

        document = item.model_dump(by_alias=True)
        document.update(
            {
                "deviceId": identity.device_id,
                "homeId": home_id,
                "tankId": channel_map[item.tank_channel],
                "bootSessionId": payload.boot_session_id,
                "receivedAt": received_at,
            }
        )
        write_batch.create(document_ref, document)

        tank_id = channel_map[item.tank_channel]
        current_latest = latest_by_tank.get(tank_id)
        if current_latest is None or item.sequence > current_latest[0]:
            latest_by_tank[tank_id] = (item.sequence, document)

    if any(item["status"] == "created" for item in accepted):
        for tank_id, (_, latest_reading) in latest_by_tank.items():
            tank_ref = (
                db.collection("homes")
                .document(home_id)
                .collection("tanks")
                .document(tank_id)
            )
            write_batch.set(
                tank_ref,
                {
                    "deviceId": identity.device_id,
                    "latestReading": latest_reading,
                    "lastCommunicationAt": received_at,
                    "status": "active",
                },
                merge=True,
            )
        write_batch.commit()

    return jsonify({"accepted": accepted, "receivedAt": received_at.isoformat()}), 202


@app.route("/v1/device/events", methods=["POST", "OPTIONS"])
def ingest_event():
    if request.method == "OPTIONS":
        return "", 204

    db = get_firestore_client()
    identity = require_device(request, db)
    payload = DeviceEvent.model_validate(request.get_json(silent=False))
    if payload.device_id != identity.device_id:
        return _json_error("deviceId no coincide con la credencial.", 403)

    received_at = datetime.now(UTC)
    event_id = (
        f"{identity.device_id}:{payload.boot_session_id or 'boot'}:"
        f"{payload.sequence if payload.sequence is not None else int(received_at.timestamp() * 1000)}:"
        f"{payload.event_type}"
    )
    document = payload.model_dump(by_alias=True)
    document.update(
        {
            "deviceId": identity.device_id,
            "homeId": identity.data.get("homeId"),
            "receivedAt": received_at,
        }
    )
    db.collection("deviceEvents").document(event_id).set(document)
    return jsonify({"accepted": True, "eventId": event_id}), 202


@app.route("/v1/device/config", methods=["GET", "OPTIONS"])
def device_config():
    if request.method == "OPTIONS":
        return "", 204

    db = get_firestore_client()
    identity = require_device(request, db)
    return jsonify(
        {
            "deviceId": identity.device_id,
            "sampleIntervalSeconds": identity.data.get("sampleIntervalSeconds", 30),
            "channels": identity.data.get("channels", []),
            "configVersion": identity.data.get("configVersion", 1),
        }
    )
