from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schemas import DeviceClaim, HomeSetup, ReadingBatch


def test_valid_reading_batch() -> None:
    batch = ReadingBatch.model_validate(
        {
            "deviceId": "dev_01",
            "bootSessionId": "boot_01",
            "readings": [
                {
                    "sequence": 42,
                    "tankChannel": "A",
                    "observedAt": datetime.now(UTC).isoformat(),
                    "timestampQuality": "verified",
                    "pressureKpa": 13.4,
                    "liters": 276,
                    "wifiRssi": -62,
                }
            ],
        }
    )
    assert batch.readings[0].tank_channel == "A"


def test_rejects_timestamp_without_timezone() -> None:
    with pytest.raises(ValidationError):
        ReadingBatch.model_validate(
            {
                "deviceId": "dev_01",
                "readings": [
                    {
                        "sequence": 42,
                        "tankChannel": "A",
                        "observedAt": "2026-08-18T15:20:00",
                        "timestampQuality": "verified",
                        "pressureKpa": 13.4,
                    }
                ],
            }
        )


def test_home_setup_requires_real_tank_dimensions() -> None:
    with pytest.raises(ValidationError):
        HomeSetup.model_validate(
            {
                "name": "Mi casa",
                "timezone": "America/Caracas",
                "tanks": [
                    {
                        "name": "Tanque principal",
                        "heightCm": 0,
                        "diameterCm": 51,
                        "capacityLiters": 408,
                    }
                ],
            }
        )


def test_device_claim_requires_efuse_based_device_id() -> None:
    claim = DeviceClaim.model_validate(
        {
            "deviceId": "smarttank-84f703123456",
            "setupPin": "12345678",
            "label": "SmartTank del patio",
        }
    )
    assert claim.device_id == "smarttank-84f703123456"

    with pytest.raises(ValidationError):
        DeviceClaim.model_validate(
            {
                "deviceId": "dev_0123456789abcdef",
                "setupPin": "12345678",
                "label": "SmartTank del patio",
            }
        )
