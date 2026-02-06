"""Seed default settings

Revision ID: 002
Revises: 001
Create Date: 2026-02-05 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


# Settings definitions from app/services/settings_definitions.py
# All settings are safe to seed (no secrets or URLs)
SETTINGS = [
    # Log retention
    {
        "key": "logs.retention_days",
        "value": "30",
        "value_type": "int",
        "category": "logs",
        "description": "Number of days to retain logs",
        "env_fallback": "LOG_RETENTION_DAYS",
        "requires_reload": False,
        "is_secret": False,
    },
    {
        "key": "logs.max_batch_size",
        "value": "1000",
        "value_type": "int",
        "category": "logs",
        "description": "Maximum batch size for log ingestion",
        "env_fallback": "LOG_MAX_BATCH_SIZE",
        "requires_reload": False,
        "is_secret": False,
    },
    {
        "key": "logs.query_limit",
        "value": "1000",
        "value_type": "int",
        "category": "logs",
        "description": "Maximum number of logs returned per query",
        "env_fallback": "LOG_QUERY_LIMIT",
        "requires_reload": False,
        "is_secret": False,
    },
    # Server configuration
    {
        "key": "server.port",
        "value": "8006",
        "value_type": "int",
        "category": "server",
        "description": "API server port",
        "env_fallback": "LOG_SERVER_PORT",
        "requires_reload": True,
        "is_secret": False,
    },
    # Auth cache
    {
        "key": "auth.cache_ttl_seconds",
        "value": "60",
        "value_type": "int",
        "category": "auth",
        "description": "Node auth validation cache TTL in seconds",
        "env_fallback": "CACHE_TTL_SECONDS",
        "requires_reload": False,
        "is_secret": False,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == 'postgresql'

    for setting in SETTINGS:
        if is_postgres:
            conn.execute(
                sa.text("""
                    INSERT INTO settings (key, value, value_type, category, description,
                                         env_fallback, requires_reload, is_secret,
                                         household_id, node_id, user_id)
                    VALUES (:key, :value, :value_type, :category, :description,
                           :env_fallback, :requires_reload, :is_secret,
                           NULL, NULL, NULL)
                    ON CONFLICT (key, household_id, node_id, user_id) DO NOTHING
                """),
                setting
            )
        else:
            conn.execute(
                sa.text("""
                    INSERT OR IGNORE INTO settings (key, value, value_type, category, description,
                                                   env_fallback, requires_reload, is_secret,
                                                   household_id, node_id, user_id)
                    VALUES (:key, :value, :value_type, :category, :description,
                           :env_fallback, :requires_reload, :is_secret,
                           NULL, NULL, NULL)
                """),
                setting
            )


def downgrade() -> None:
    conn = op.get_bind()
    for setting in SETTINGS:
        conn.execute(
            sa.text("""
                DELETE FROM settings
                WHERE key = :key
                  AND household_id IS NULL
                  AND node_id IS NULL
                  AND user_id IS NULL
            """),
            {"key": setting["key"]}
        )
