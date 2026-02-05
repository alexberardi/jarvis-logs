"""Settings service for jarvis-logs.

Provides runtime configuration that can be modified without restarting.
Settings are stored in the database with fallback to environment variables.
"""

import logging
from typing import Any

from jarvis_settings_client import SettingsService as BaseSettingsService

from app.services.settings_definitions import SETTINGS_DEFINITIONS

logger = logging.getLogger(__name__)


class LogsSettingsService(BaseSettingsService):
    """Settings service for Logs with helper methods."""

    def get_logs_config(self) -> dict[str, Any]:
        """Get logs configuration."""
        return {
            "retention_days": self.get_int("logs.retention_days", 30),
            "max_batch_size": self.get_int("logs.max_batch_size", 1000),
            "query_limit": self.get_int("logs.query_limit", 1000),
        }


# Global singleton
_settings_service: LogsSettingsService | None = None


def get_settings_service() -> LogsSettingsService:
    """Get the global SettingsService instance."""
    global _settings_service
    if _settings_service is None:
        from app.db.models import Setting
        from app.db.session import get_session_local

        SessionLocal = get_session_local()
        _settings_service = LogsSettingsService(
            definitions=SETTINGS_DEFINITIONS,
            get_db_session=SessionLocal,
            setting_model=Setting,
        )
    return _settings_service


def reset_settings_service() -> None:
    """Reset the settings service singleton (for testing)."""
    global _settings_service
    _settings_service = None
