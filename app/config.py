"""Single environment-backed application configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_port: int
    reconnect_attempts: int
    reconnect_base_delay: float
    log_level: str
    api_key: str
    cors_origins: tuple[str, ...]
    max_num_bars: int
    max_history_range_days: int
    server_utc_offset_seconds: int

    @classmethod
    def from_env(cls):
        settings = cls(
            api_port=int(os.getenv("MT5_API_PORT", "5001")),
            reconnect_attempts=int(os.getenv("MT5_RECONNECT_ATTEMPTS", "3")),
            reconnect_base_delay=float(os.getenv("MT5_RECONNECT_BASE_DELAY", "1.0")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            api_key=os.getenv("API_KEY", ""),
            cors_origins=tuple(
                value.strip()
                for value in os.getenv("CORS_ORIGINS", "").split(",")
                if value.strip()
            ),
            max_num_bars=int(os.getenv("MAX_NUM_BARS", "10000")),
            max_history_range_days=int(os.getenv("MAX_HISTORY_RANGE_DAYS", "31")),
            server_utc_offset_seconds=int(
                os.getenv("MT5_SERVER_UTC_OFFSET_SECONDS", "0")
            ),
        )
        settings.validate()
        return settings

    def validate(self):
        if self.reconnect_attempts < 1:
            raise ValueError("MT5_RECONNECT_ATTEMPTS must be at least 1")
        if self.reconnect_base_delay <= 0:
            raise ValueError("MT5_RECONNECT_BASE_DELAY must be positive")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid LOG_LEVEL: {self.log_level}")
