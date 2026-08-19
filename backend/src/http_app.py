from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite, pi
from typing import Any

from flask import Flask, jsonify, request
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import ValidationError

from .auth import AuthenticationError, require_device, require_user
from .config import settings
from .database import get_firestore_client
from .device_claim import verify_setup_pin
from .schemas import DeviceClaim, DeviceEvent, HomeSetup, ReadingBatch, TankUpdate

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
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
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


def _tank_document_id(device_id: str, sensor_id: str) -> str:
    return f"{device_id}:{sensor_id}"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _tank_dimensions(data: dict[str, Any]) -> tuple[float, float] | None:
    height_cm = _number(data.get("heightCm"))
    diameter_cm = _number(data.get("diameterCm"))
    if not height_cm or not diameter_cm:
        return None
    return height_cm, diameter_cm


def _tank_calibration(data: dict[str, Any]) -> tuple[float, float, float] | None:
    dimensions = _tank_dimensions(data)
    full_pressure_kpa = _number(data.get("fullPressureKpa"))
    if dimensions is None or not full_pressure_kpa:
        return None
    return *dimensions, full_pressure_kpa


def _capacity_liters(height_cm: float, diameter_cm: float) -> float:
    return round(pi * (diameter_cm / 2) ** 2 * height_cm / 1000, 2)


def _derive_reading(
    reading: dict[str, Any],
    tank_data: dict[str, Any],
) -> dict[str, Any]:
    derived = dict(reading)
    for field in ("percentage", "waterHeightCm", "liters"):
        derived.pop(field, None)

    calibration = _tank_calibration(tank_data)
    pressure_kpa = _number(derived.get("pressureKpa"))
    if calibration is None or pressure_kpa is None:
        return derived

    height_cm, diameter_cm, full_pressure_kpa = calibration
    percentage = min(max(pressure_kpa / full_pressure_kpa * 100, 0), 100)
    capacity_liters = _capacity_liters(height_cm, diameter_cm)
    derived.update(
        {
            "percentage": round(percentage, 2),
            "waterHeightCm": round(height_cm * percentage / 100, 2),
            "liters": round(capacity_liters * percentage / 100, 2),
        }
    )
    return derived


def _tank_response(tank_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": tank_id,
        "deviceId": data.get("deviceId"),
        "sensorId": data.get("sensorId"),
        "name": data.get("name") or f"Tanque {data.get('sensorId', '')}".strip(),
        "shape": data.get("shape"),
        "heightCm": data.get("heightCm"),
        "diameterCm": data.get("diameterCm"),
        "fullPressureKpa": data.get("fullPressureKpa"),
        "capacityLiters": data.get("capacityLiters"),
        "lowLevelPercentage": data.get("lowLevelPercentage", 25),
        "configurationStatus": data.get("configurationStatus", "pending"),
        "status": data.get("status", "active"),
    }


def _device_response(device_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": device_id,
        "label": data.get("label", "SmartTank"),
        "status": data.get("status"),
        "firmwareVersion": data.get("firmwareVersion"),
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
    tanks = []
    for snapshot in home_ref.collection("tanks").stream():
        tank_data = snapshot.to_dict() or {}
        if tank_data.get("deviceId") and tank_data.get("sensorId"):
            tanks.append(_tank_response(snapshot.id, tank_data))
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
                "tanks": [],
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


@app.route("/v1/homes/<home_id>/tanks/<tank_id>", methods=["PATCH", "OPTIONS"])
def update_tank(home_id: str, tank_id: str):
    if request.method == "OPTIONS":
        return "", 204

    db = get_firestore_client()
    _, user_id = _authenticated_user()
    if not _home_manager_role(db, user_id, home_id):
        return _json_error("Solo un propietario o administrador puede editar tanques.", 403)

    payload = TankUpdate.model_validate(request.get_json(silent=False))
    tank_ref = db.collection("homes").document(home_id).collection("tanks").document(tank_id)
    tank_snapshot = tank_ref.get()
    if not tank_snapshot.exists:
        return _json_error("El tanque no existe o todavía no ha enviado mediciones.", 404)

    tank_data = tank_snapshot.to_dict() or {}
    if not tank_data.get("deviceId") or not tank_data.get("sensorId"):
        return _json_error("El tanque no fue descubierto desde un sensor válido.", 409)

    updated_at = datetime.now(UTC)
    requested = payload.model_dump(by_alias=True, exclude_none=True)
    configured_tank = {**tank_data, **requested}
    dimensions = _tank_dimensions(configured_tank)
    calibration = _tank_calibration(configured_tank)
    update = {**requested, "updatedAt": updated_at}
    if dimensions is not None:
        height_cm, diameter_cm = dimensions
        update.update(
            {
                "shape": "cylinder",
                "capacityLiters": _capacity_liters(height_cm, diameter_cm),
            }
        )
    update["configurationStatus"] = (
        "configured" if calibration is not None else "pending"
    )

    latest_reading = tank_data.get("latestReading")
    if isinstance(latest_reading, dict):
        update["latestReading"] = _derive_reading(
            latest_reading,
            {**configured_tank, **update},
        )

    audit_ref = db.collection("auditLogs").document()
    write_batch = db.batch()
    write_batch.set(tank_ref, update, merge=True)
    write_batch.create(
        audit_ref,
        {
            "action": "tank_updated",
            "tankId": tank_id,
            "deviceId": tank_data.get("deviceId"),
            "sensorId": tank_data.get("sensorId"),
            "homeId": home_id,
            "actorUserId": user_id,
            "changedFields": sorted(requested),
            "createdAt": updated_at,
        },
    )
    write_batch.commit()
    tank_data.update(update)
    return jsonify({"tank": _tank_response(tank_id, tank_data)})


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

    update = {
        "homeId": home_id,
        "label": payload.label,
        "status": "active",
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

    received_at = datetime.now(UTC)
    refs = [
        db.collection("readings").document(
            f"{identity.device_id}:{item.sequence}:{item.sensor_id}"
        )
        for item in payload.readings
    ]
    tank_refs_by_sensor = {
        sensor_id: (
            db.collection("homes")
            .document(home_id)
            .collection("tanks")
            .document(_tank_document_id(identity.device_id, sensor_id))
        )
        for sensor_id in {item.sensor_id for item in payload.readings}
    }
    existing_ids = {snapshot.id for snapshot in db.get_all(refs) if snapshot.exists}
    existing_tanks = {
        snapshot.id: snapshot.to_dict() or {}
        for snapshot in db.get_all(list(tank_refs_by_sensor.values()))
        if snapshot.exists
    }
    write_batch = db.batch()
    accepted: list[dict[str, Any]] = []
    latest_by_tank: dict[str, tuple[int, str, dict[str, Any]]] = {}

    for item, document_ref in zip(payload.readings, refs, strict=True):
        status = "duplicate" if document_ref.id in existing_ids else "created"
        accepted.append(
            {"sequence": item.sequence, "sensorId": item.sensor_id, "status": status}
        )
        if status == "duplicate":
            continue

        tank_id = _tank_document_id(identity.device_id, item.sensor_id)
        document = _derive_reading(
            item.model_dump(by_alias=True),
            existing_tanks.get(tank_id, {}),
        )
        document.update(
            {
                "deviceId": identity.device_id,
                "homeId": home_id,
                "tankId": tank_id,
                "bootSessionId": payload.boot_session_id,
                "receivedAt": received_at,
            }
        )
        write_batch.create(document_ref, document)

        current_latest = latest_by_tank.get(tank_id)
        if current_latest is None or item.sequence > current_latest[0]:
            latest_by_tank[tank_id] = (item.sequence, item.sensor_id, document)

    for tank_id, (_, sensor_id, latest_reading) in latest_by_tank.items():
        tank_document = {
            "deviceId": identity.device_id,
            "sensorId": sensor_id,
            "latestReading": latest_reading,
            "lastCommunicationAt": received_at,
            "status": "active",
            "updatedAt": received_at,
        }
        if tank_id not in existing_tanks:
            tank_document.update(
                {
                    "homeId": home_id,
                    "name": f"Tanque {sensor_id}",
                    "configurationStatus": "pending",
                    "lowLevelPercentage": 25,
                    "discoveredAt": received_at,
                    "createdAt": received_at,
                }
            )
        write_batch.set(tank_refs_by_sensor[sensor_id], tank_document, merge=True)

    write_batch.set(
        db.collection("devices").document(identity.device_id),
        {"lastSeenAt": received_at, "updatedAt": received_at},
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
            "sensorMode": "discovery",
            "configVersion": identity.data.get("configVersion", 1),
        }
    )
