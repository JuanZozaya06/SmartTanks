from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    allowed_origins: tuple[str, ...]
    max_batch_size: int


def load_settings() -> Settings:
    origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:4200,https://juanzozaya06.github.io",
    )
    return Settings(
        allowed_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        max_batch_size=int(os.getenv("MAX_BATCH_SIZE", "100")),
    )


settings = load_settings()
