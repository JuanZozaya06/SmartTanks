import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "demo-smart-tanks")

from src.auth import DeviceIdentity
from src.device_claim import create_factory_credentials
from src.http_app import app


@dataclass
class FakeSnapshot:
    id: str
    exists: bool = False
    data: dict[str, Any] | None = None

    def to_dict(self):
        return self.data


class FakeDocumentReference:
    def __init__(self, database, path: str):
        self.database = database
        self.path = path
        self.id = path.rsplit("/", maxsplit=1)[-1]

    def collection(self, name: str):
        return FakeCollectionReference(self.database, f"{self.path}/{name}")

    def get(self):
        data = self.database.documents.get(self.path)
        return FakeSnapshot(self.id, data is not None, data)

    def update(self, document):
        self.database.documents.setdefault(self.path, {}).update(document)


class FakeCollectionReference:
    def __init__(self, database, path: str, filters=None, ordering=None):
        self.database = database
        self.path = path
        self.filters = filters or []
        self.ordering = ordering

    def document(self, document_id: str | None = None):
        return FakeDocumentReference(
            self.database,
            f"{self.path}/{document_id or self.database.generated_document_id}",
        )

    def stream(self):
        prefix = f"{self.path}/"
        expected_segments = len(self.path.split("/")) + 1
        snapshots = [
            FakeSnapshot(path.rsplit("/", maxsplit=1)[-1], True, data)
            for path, data in self.database.documents.items()
            if path.startswith(prefix) and len(path.split("/")) == expected_segments
        ]
        for field_path, operator, expected in self.filters:
            snapshots = [
                snapshot
                for snapshot in snapshots
                if self._matches((snapshot.data or {}).get(field_path), operator, expected)
            ]
        if self.ordering:
            field_path, direction = self.ordering
            snapshots.sort(
                key=lambda snapshot: (snapshot.data or {}).get(field_path),
                reverse=direction == "DESCENDING",
            )
        return snapshots

    def where(self, *, filter):
        return FakeCollectionReference(
            self.database,
            self.path,
            [*self.filters, (filter.field_path, filter.op_string, filter.value)],
            self.ordering,
        )

    def order_by(self, field_path, direction="ASCENDING"):
        return FakeCollectionReference(
            self.database,
            self.path,
            self.filters,
            (field_path, direction),
        )

    @staticmethod
    def _matches(value, operator, expected):
        if value is None:
            return False
        if operator == "==":
            return value == expected
        if operator == ">=":
            return value >= expected
        if operator == "<=":
            return value <= expected
        raise AssertionError(f"Operador no soportado por el doble: {operator}")


class FakeWriteBatch:
    def __init__(self):
        self.creates: list[tuple[FakeDocumentReference, dict[str, Any]]] = []
        self.sets: list[tuple[FakeDocumentReference, dict[str, Any], bool]] = []
        self.committed = False

    def create(self, reference, document):
        self.creates.append((reference, document))

    def set(self, reference, document, merge=False):
        self.sets.append((reference, document, merge))

    def commit(self):
        self.committed = True


class FakeFirestore:
    def __init__(self, documents: dict[str, dict[str, Any]] | None = None):
        self.write_batch = FakeWriteBatch()
        self.documents = documents or {}
        self.generated_document_id = "home_generated"

    def collection(self, name: str):
        return FakeCollectionReference(self, name)

    def get_all(self, references):
        snapshots = []
        for reference in references:
            data = self.documents.get(reference.path)
            snapshots.append(FakeSnapshot(reference.id, data is not None, data))
        return snapshots

    def batch(self):
        return self.write_batch


def test_health_endpoint() -> None:
    response = app.test_client().get("/v1/health")

    assert response.status_code == 200
    assert response.get_json() == {"service": "smart-tanks-api", "status": "ok"}


def test_github_pages_origin_is_allowed() -> None:
    response = app.test_client().options(
        "/v1/homes/home_01/tanks/tank_01",
        headers={
            "Origin": "https://juanzozaya06.github.io",
            "Access-Control-Request-Method": "PATCH",
        },
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == (
        "https://juanzozaya06.github.io"
    )
    assert "PATCH" in response.headers["Access-Control-Allow-Methods"]


def test_reading_batch_updates_history_and_latest_tank_state(monkeypatch) -> None:
    database = FakeFirestore()
    identity = DeviceIdentity(
        device_id="dev_01",
        data={"homeId": "home_01"},
    )
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_device", lambda request, db: identity)

    response = app.test_client().post(
        "/v1/device/readings/batch",
        json={
            "deviceId": "dev_01",
            "bootSessionId": "boot_01",
            "readings": [
                {
                    "sequence": 41,
                    "sensorId": "pressure-a",
                    "observedAt": "2026-08-18T15:19:30Z",
                    "timestampQuality": "verified",
                    "pressureKpa": 13.1,
                    "percentage": 67,
                    "liters": 273,
                },
                {
                    "sequence": 42,
                    "sensorId": "pressure-a",
                    "observedAt": "2026-08-18T15:20:00Z",
                    "timestampQuality": "verified",
                    "pressureKpa": 13.4,
                    "percentage": 68.3,
                    "liters": 276,
                },
                {
                    "sequence": 42,
                    "sensorId": "pressure-b",
                    "observedAt": "2026-08-18T15:20:00Z",
                    "timestampQuality": "verified",
                    "pressureKpa": 6.7,
                    "percentage": 34.1,
                    "liters": 139,
                },
            ],
        },
    )

    assert response.status_code == 202
    assert database.write_batch.committed
    assert len(database.write_batch.creates) == 3
    assert [reference.path for reference, _, _ in database.write_batch.sets] == [
        "homes/home_01/tanks/dev_01:pressure-a",
        "homes/home_01/tanks/dev_01:pressure-b",
        "devices/dev_01",
    ]
    tank_1_state = database.write_batch.sets[0][1]
    assert database.write_batch.sets[0][2] is True
    assert tank_1_state["latestReading"]["sequence"] == 42
    assert "percentage" not in tank_1_state["latestReading"]
    assert "liters" not in tank_1_state["latestReading"]


def test_reading_uses_the_saved_tank_calibration(monkeypatch) -> None:
    tank_path = "homes/home_01/tanks/dev_01:pressure-a"
    database = FakeFirestore(
        {
            tank_path: {
                "deviceId": "dev_01",
                "sensorId": "pressure-a",
                "heightCm": 200,
                "diameterCm": 100,
                "fullPressureKpa": 19.6133,
                "configurationStatus": "configured",
            }
        }
    )
    identity = DeviceIdentity(device_id="dev_01", data={"homeId": "home_01"})
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_device", lambda request, db: identity)

    response = app.test_client().post(
        "/v1/device/readings/batch",
        json={
            "deviceId": "dev_01",
            "readings": [
                {
                    "sequence": 44,
                    "sensorId": "pressure-a",
                    "timestampQuality": "pending",
                    "pressureKpa": 9.80665,
                    "percentage": 1,
                    "waterHeightCm": 1,
                    "liters": 1,
                }
            ],
        },
    )

    assert response.status_code == 202
    historical = database.write_batch.creates[0][1]
    assert historical["percentage"] == 50
    assert historical["waterHeightCm"] == 100
    assert historical["liters"] == 785.4
    assert database.write_batch.sets[0][1]["latestReading"] == historical


def test_reading_keeps_the_custom_name_of_an_existing_sensor(monkeypatch) -> None:
    tank_path = "homes/home_01/tanks/dev_01:pressure-a"
    database = FakeFirestore(
        {
            tank_path: {
                "deviceId": "dev_01",
                "sensorId": "pressure-a",
                "name": "Tanque del patio",
            }
        }
    )
    identity = DeviceIdentity(device_id="dev_01", data={"homeId": "home_01"})
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_device", lambda request, db: identity)

    response = app.test_client().post(
        "/v1/device/readings/batch",
        json={
            "deviceId": "dev_01",
            "readings": [
                {
                    "sequence": 43,
                    "sensorId": "pressure-a",
                    "timestampQuality": "pending",
                    "pressureKpa": 13.5,
                }
            ],
        },
    )

    assert response.status_code == 202
    assert "name" not in database.write_batch.sets[0][1]


def test_authenticated_user_can_create_home_without_tanks(monkeypatch) -> None:
    database = FakeFirestore()
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr(
        "src.http_app.require_user",
        lambda request: {
            "uid": "user_01",
            "email": "zozi@example.com",
            "name": "Zozi",
        },
    )

    response = app.test_client().post(
        "/v1/homes",
        json={
            "name": "Mi casa",
            "timezone": "America/Caracas",
            "displayName": "Zozi",
        },
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["home"]["id"] == "home_generated"
    assert body["home"]["role"] == "owner"
    assert body["tanks"] == []
    assert database.write_batch.committed
    assert [reference.path for reference, _, _ in database.write_batch.sets] == [
        "homes/home_generated",
        "homes/home_generated/members/user_01",
        "users/user_01",
    ]


def test_user_context_returns_active_home(monkeypatch) -> None:
    database = FakeFirestore(
        {
            "users/user_01": {
                "displayName": "Zozi",
                "email": "zozi@example.com",
                "activeHomeId": "home_01",
            },
            "homes/home_01": {
                "name": "Mi casa",
                "timezone": "America/Caracas",
            },
            "homes/home_01/members/user_01": {"role": "owner"},
            "homes/home_01/tanks/smarttank-84f703123456:pressure-a": {
                "deviceId": "smarttank-84f703123456",
                "sensorId": "pressure-a",
                "name": "Tanque principal",
                "shape": "cylinder",
                "heightCm": 200,
                "diameterCm": 51,
                "capacityLiters": 408,
                "lowLevelPercentage": 25,
            },
        }
    )
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr(
        "src.http_app.require_user",
        lambda request: {"uid": "user_01", "email": "zozi@example.com"},
    )

    response = app.test_client().get("/v1/me/context")

    assert response.status_code == 200
    body = response.get_json()
    assert body["home"] == {
        "id": "home_01",
        "name": "Mi casa",
        "timezone": "America/Caracas",
        "role": "owner",
    }
    assert body["tanks"][0]["id"] == "smarttank-84f703123456:pressure-a"


def test_user_can_read_bucketed_tank_history_with_current_calibration(monkeypatch) -> None:
    tank_id = "smarttank-84f703123456:pressure-a"
    database = FakeFirestore(
        {
            "users/user_01": {"activeHomeId": "home_01"},
            "homes/home_01/members/user_01": {"role": "viewer"},
            f"homes/home_01/tanks/{tank_id}": {
                "deviceId": "smarttank-84f703123456",
                "sensorId": "pressure-a",
                "name": "Tanque principal",
                "heightCm": 200,
                "diameterCm": 51,
                "fullPressureKpa": 19.6,
                "configurationStatus": "configured",
            },
            "readings/reading_01": {
                "homeId": "home_01",
                "tankId": tank_id,
                "observedAt": datetime(2026, 8, 19, 12, 1, tzinfo=UTC),
                "timestampQuality": "verified",
                "pressureKpa": 9.8,
            },
            "readings/reading_02": {
                "homeId": "home_01",
                "tankId": tank_id,
                "observedAt": datetime(2026, 8, 19, 12, 4, tzinfo=UTC),
                "timestampQuality": "estimated",
                "pressureKpa": 19.6,
            },
            "readings/reading_03": {
                "homeId": "home_01",
                "tankId": tank_id,
                "observedAt": datetime(2026, 8, 19, 12, 6, tzinfo=UTC),
                "timestampQuality": "verified",
                "pressureKpa": 4.9,
            },
            "readings/other_tank": {
                "homeId": "home_01",
                "tankId": "another-tank",
                "observedAt": datetime(2026, 8, 19, 12, 2, tzinfo=UTC),
                "timestampQuality": "verified",
                "pressureKpa": 12,
            },
        }
    )
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_user", lambda request: {"uid": "user_01"})

    response = app.test_client().get(
        f"/v1/tanks/{tank_id}/readings",
        query_string={
            "from": "2026-08-19T12:00:00Z",
            "to": "2026-08-19T13:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["period"] == "custom"
    assert body["bucketSeconds"] == 300
    assert body["sampleCount"] == 3
    assert len(body["points"]) == 2
    assert body["points"][0]["percentage"] == 75
    assert body["points"][0]["liters"] == 306.42
    assert body["points"][0]["timestampQuality"] == "estimated"
    assert body["points"][1]["percentage"] == 25


def test_tank_history_rejects_ranges_longer_than_31_days(monkeypatch) -> None:
    tank_id = "smarttank-84f703123456:pressure-a"
    database = FakeFirestore(
        {
            "users/user_01": {"activeHomeId": "home_01"},
            "homes/home_01/members/user_01": {"role": "owner"},
            f"homes/home_01/tanks/{tank_id}": {
                "deviceId": "smarttank-84f703123456",
                "sensorId": "pressure-a",
            },
        }
    )
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_user", lambda request: {"uid": "user_01"})

    response = app.test_client().get(
        f"/v1/tanks/{tank_id}/readings",
        query_string={
            "from": "2026-07-01T00:00:00Z",
            "to": "2026-08-19T00:00:00Z",
        },
    )

    assert response.status_code == 422
    assert "31 días" in response.get_json()["error"]["message"]


def test_tank_history_requires_active_home_membership(monkeypatch) -> None:
    database = FakeFirestore(
        {"users/user_01": {"activeHomeId": "home_without_membership"}}
    )
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_user", lambda request: {"uid": "user_01"})

    response = app.test_client().get("/v1/tanks/tank_01/readings?period=day")

    assert response.status_code == 403
    assert "casa activa" in response.get_json()["error"]["message"]


def test_owner_can_rename_a_discovered_tank(monkeypatch) -> None:
    tank_id = "smarttank-84f703123456:pressure-a"
    database = FakeFirestore(
        {
            "users/user_01": {"activeHomeId": "home_01"},
            "homes/home_01/members/user_01": {"role": "owner"},
            f"homes/home_01/tanks/{tank_id}": {
                "deviceId": "smarttank-84f703123456",
                "sensorId": "pressure-a",
                "name": "Tanque pressure-a",
                "status": "active",
            },
        }
    )
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_user", lambda request: {"uid": "user_01"})

    response = app.test_client().patch(
        f"/v1/homes/home_01/tanks/{tank_id}",
        json={"name": "Tanque del patio"},
    )

    assert response.status_code == 200
    assert response.get_json()["tank"]["name"] == "Tanque del patio"
    assert database.write_batch.sets[0][1]["name"] == "Tanque del patio"
    assert database.write_batch.creates[0][1]["action"] == "tank_updated"


def test_owner_can_configure_and_calibrate_a_discovered_tank(monkeypatch) -> None:
    tank_id = "smarttank-84f703123456:pressure-a"
    database = FakeFirestore(
        {
            "users/user_01": {"activeHomeId": "home_01"},
            "homes/home_01/members/user_01": {"role": "owner"},
            f"homes/home_01/tanks/{tank_id}": {
                "deviceId": "smarttank-84f703123456",
                "sensorId": "pressure-a",
                "name": "Tanque pressure-a",
                "status": "active",
                "latestReading": {"sequence": 42, "pressureKpa": 9.8},
            },
        }
    )
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_user", lambda request: {"uid": "user_01"})

    response = app.test_client().patch(
        f"/v1/homes/home_01/tanks/{tank_id}",
        json={
            "name": "Tanque principal",
            "heightCm": 200,
            "diameterCm": 51,
            "fullPressureKpa": 19.6,
        },
    )

    assert response.status_code == 200
    update = database.write_batch.sets[0][1]
    assert update["shape"] == "cylinder"
    assert update["capacityLiters"] == 408.56
    assert update["configurationStatus"] == "configured"
    assert update["latestReading"]["percentage"] == 50
    assert update["latestReading"]["waterHeightCm"] == 100
    assert update["latestReading"]["liters"] == 204.28
    assert database.write_batch.creates[0][1]["changedFields"] == [
        "diameterCm",
        "fullPressureKpa",
        "heightCm",
        "name",
    ]


def test_owner_can_claim_factory_device_without_precreated_tanks(monkeypatch) -> None:
    credentials = create_factory_credentials("smarttank-84f703123456")
    database = FakeFirestore(
        {
            "users/user_01": {"activeHomeId": "home_01"},
            "homes/home_01/members/user_01": {"role": "owner"},
            f"devices/{credentials.device_id}": {
                "status": "unclaimed",
                "deviceSecretHash": credentials.device_secret_hash,
                "setupPinHash": credentials.setup_pin_hash,
                "setupPinSalt": credentials.setup_pin_salt,
                "claimAttempts": 0,
            },
        }
    )
    monkeypatch.setattr("src.http_app.get_firestore_client", lambda: database)
    monkeypatch.setattr("src.http_app.require_user", lambda request: {"uid": "user_01"})

    response = app.test_client().post(
        "/v1/homes/home_01/devices/claim",
        json={
            "deviceId": credentials.device_id,
            "setupPin": credentials.setup_pin,
            "label": "SmartTank del patio",
        },
    )

    assert response.status_code == 200
    claimed_update = database.write_batch.sets[0][1]
    assert claimed_update["status"] == "active"
    assert claimed_update["homeId"] == "home_01"
    assert claimed_update["label"] == "SmartTank del patio"
    assert "channels" not in claimed_update
    assert "setupPinHash" not in claimed_update
