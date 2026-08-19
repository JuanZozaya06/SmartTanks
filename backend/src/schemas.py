from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TankReading(ApiModel):
    sequence: int = Field(ge=0)
    tank_channel: str = Field(alias="tankChannel", min_length=1, max_length=16)
    observed_at: datetime | None = Field(default=None, alias="observedAt")
    timestamp_quality: Literal["verified", "estimated", "pending"] = Field(alias="timestampQuality")
    elapsed_ms: int | None = Field(default=None, alias="elapsedMs", ge=0)
    pressure_kpa: float = Field(alias="pressureKpa", ge=0, le=100)
    water_height_cm: float | None = Field(default=None, alias="waterHeightCm", ge=0)
    percentage: float | None = Field(default=None, ge=0, le=100)
    liters: float | None = Field(default=None, ge=0)
    wifi_rssi: int | None = Field(default=None, alias="wifiRssi", ge=-127, le=0)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("observedAt debe incluir zona horaria")
        return value


class ReadingBatch(ApiModel):
    device_id: str = Field(alias="deviceId", min_length=1)
    boot_session_id: str | None = Field(default=None, alias="bootSessionId", max_length=128)
    readings: list[TankReading] = Field(min_length=1, max_length=100)


class DeviceEvent(ApiModel):
    device_id: str = Field(alias="deviceId", min_length=1)
    event_type: Literal[
        "boot_started",
        "wifi_disconnected",
        "wifi_reconnected",
        "internet_disconnected",
        "sync_started",
        "sync_completed",
        "time_reconstructed",
        "sensor_error",
        "low_water_alert",
    ] = Field(alias="eventType")
    sequence: int | None = Field(default=None, ge=0)
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")
    elapsed_ms: int | None = Field(default=None, alias="elapsedMs", ge=0)
    boot_session_id: str | None = Field(default=None, alias="bootSessionId", max_length=128)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class TankSetup(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    shape: Literal["cylinder"] = "cylinder"
    height_cm: float = Field(alias="heightCm", gt=0, le=1000)
    diameter_cm: float = Field(alias="diameterCm", gt=0, le=1000)
    capacity_liters: float = Field(alias="capacityLiters", gt=0, le=100000)
    low_level_percentage: float = Field(
        default=25,
        alias="lowLevelPercentage",
        ge=0,
        le=100,
    )


class HomeSetup(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, alias="displayName", max_length=100)
    tanks: list[TankSetup] = Field(min_length=1, max_length=2)


class DeviceClaim(ApiModel):
    device_id: str = Field(alias="deviceId", pattern=r"^smarttank-[a-f0-9]{12}$")
    setup_pin: str = Field(alias="setupPin", pattern=r"^[0-9]{8}$")
    label: str = Field(min_length=1, max_length=80)
