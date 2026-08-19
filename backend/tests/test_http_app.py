import os
from dataclasses import dataclass
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
    def __init__(self, database, path: str):
        self.database = database
        self.path = path

    def document(self, document_id: str | None = None):
        return FakeDocumentReference(
            self.database,
            f"{self.path}/{document_id or self.database.generated_document_id}",
        )

    def stream(self):
        prefix = f"{self.path}/"
        expected_segments = len(self.path.split("/")) + 1
        return [
            FakeSnapshot(path.rsplit("/", maxsplit=1)[-1], True, data)
            for path, data in self.database.documents.items()
            if path.startswith(prefix) and len(path.split("/")) == expected_segments
        ]


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
        return [FakeSnapshot(reference.id) for reference in references]

    def batch(self):
        return self.write_batch


def test_health_endpoint() -> None:
    response = app.test_client().get("/v1/health")

    assert response.status_code == 200
    assert response.get_json() == {"service": "smart-tanks-api", "status": "ok"}


def test_reading_batch_updates_history_and_latest_tank_state(monkeypatch) -> None:
    database = FakeFirestore()
    identity = DeviceIdentity(
        device_id="dev_01",
        data={
            "homeId": "home_01",
            "channels": [
                {"channel": "A", "tankId": "tank_1"},
                {"channel": "B", "tankId": "tank_2"},
            ],
        },
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
                    "tankChannel": "A",
                    "observedAt": "2026-08-18T15:19:30Z",
                    "timestampQuality": "verified",
                    "pressureKpa": 13.1,
                    "percentage": 67,
                    "liters": 273,
                },
                {
                    "sequence": 42,
                    "tankChannel": "A",
                    "observedAt": "2026-08-18T15:20:00Z",
                    "timestampQuality": "verified",
                    "pressureKpa": 13.4,
                    "percentage": 68.3,
                    "liters": 276,
                },
                {
                    "sequence": 42,
                    "tankChannel": "B",
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
        "homes/home_01/tanks/tank_1",
        "homes/home_01/tanks/tank_2",
    ]
    tank_1_state = database.write_batch.sets[0][1]
    assert database.write_batch.sets[0][2] is True
    assert tank_1_state["latestReading"]["sequence"] == 42
    assert tank_1_state["latestReading"]["liters"] == 276


def test_authenticated_user_can_create_home_and_tanks(monkeypatch) -> None:
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
            "tanks": [
                {
                    "name": "Tanque principal",
                    "heightCm": 200,
                    "diameterCm": 51,
                    "capacityLiters": 408,
                    "lowLevelPercentage": 25,
                },
                {
                    "name": "Tanque auxiliar",
                    "heightCm": 200,
                    "diameterCm": 51,
                    "capacityLiters": 408,
                    "lowLevelPercentage": 30,
                },
            ],
        },
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["home"]["id"] == "home_generated"
    assert body["home"]["role"] == "owner"
    assert [tank["id"] for tank in body["tanks"]] == ["tank_1", "tank_2"]
    assert database.write_batch.committed
    assert [reference.path for reference, _, _ in database.write_batch.sets] == [
        "homes/home_generated",
        "homes/home_generated/members/user_01",
        "users/user_01",
        "homes/home_generated/tanks/tank_1",
        "homes/home_generated/tanks/tank_2",
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
            "homes/home_01/tanks/tank_1": {
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
    assert body["tanks"][0]["id"] == "tank_1"


def test_owner_can_claim_factory_device_and_map_tank_channels(monkeypatch) -> None:
    credentials = create_factory_credentials("smarttank-84f703123456")
    database = FakeFirestore(
        {
            "users/user_01": {"activeHomeId": "home_01"},
            "homes/home_01/members/user_01": {"role": "owner"},
            "homes/home_01/tanks/tank_1": {"name": "Principal"},
            "homes/home_01/tanks/tank_2": {"name": "Auxiliar"},
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
    assert claimed_update["channels"] == [
        {"channel": "A", "tankId": "tank_1"},
        {"channel": "B", "tankId": "tank_2"},
    ]
    assert "setupPinHash" not in claimed_update
