"""Settings definitions for jarvis-logs.

Defines all configurable settings with their types, defaults, and metadata.
"""

from jarvis_settings_client import SettingDefinition


SETTINGS_DEFINITIONS: list[SettingDefinition] = [
    # Log retention
    SettingDefinition(
        key="logs.retention_days",
        category="logs",
        value_type="int",
        default=30,
        description="Number of days to retain logs",
        env_fallback="LOG_RETENTION_DAYS",
    ),
    SettingDefinition(
        key="logs.max_batch_size",
        category="logs",
        value_type="int",
        default=1000,
        description="Maximum batch size for log ingestion",
        env_fallback="LOG_MAX_BATCH_SIZE",
    ),
    SettingDefinition(
        key="logs.query_limit",
        category="logs",
        value_type="int",
        default=1000,
        description="Maximum number of logs returned per query",
        env_fallback="LOG_QUERY_LIMIT",
    ),

    # Server configuration
    SettingDefinition(
        key="server.port",
        category="server",
        value_type="int",
        default=7702,
        description="API server port",
        env_fallback="LOG_SERVER_PORT",
        requires_reload=True,
    ),

    # Auth cache
    SettingDefinition(
        key="auth.cache_ttl_seconds",
        category="auth",
        value_type="int",
        default=60,
        description="Node auth validation cache TTL in seconds",
        env_fallback="CACHE_TTL_SECONDS",
    ),
]
