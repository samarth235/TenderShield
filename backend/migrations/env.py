"""Alembic environment: migrates the database named by TS_DATABASE_URL."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.schema import metadata

config = context.config
target_metadata = metadata


def run_migrations_offline() -> None:
    context.configure(url=get_settings().sqlalchemy_url, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Callers (app.db.init_db) may pass an open connection so migrations share it.
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(get_settings().sqlalchemy_url)
    with engine.begin() as conn:
        _run(conn)
    engine.dispose()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
