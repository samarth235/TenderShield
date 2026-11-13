"""Migrations and the schema module must describe the same database; the Postgres adapter's SQL translation."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.config import get_settings
from app.db import init_db
from app.pg import Row, translate
from app.schema import metadata


def test_migrations_match_schema():
    init_db()
    engine = create_engine(get_settings().sqlalchemy_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), metadata)
    finally:
        engine.dispose()
    assert diff == [], f"Schema drift - add an Alembic migration: {diff}"


def test_translate_placeholders_and_like():
    sql, serial = translate("SELECT * FROM market_awards WHERE supplier_name LIKE '%JV?%' AND country = ?")
    assert sql == "SELECT * FROM market_awards WHERE supplier_name ILIKE '%%JV?%%' AND country = %s"
    assert serial is None


def test_translate_upsert_uses_primary_key():
    sql, _ = translate("INSERT OR REPLACE INTO artifacts (tender_id, stage, body, created_at) VALUES (?, ?, ?, ?)")
    assert sql.endswith("ON CONFLICT (tender_id, stage) DO UPDATE SET body = EXCLUDED.body, created_at = EXCLUDED.created_at")


def test_translate_upsert_without_column_list():
    sql, _ = translate("INSERT OR REPLACE INTO market_sources VALUES (" + ",".join("?" * 11) + ")")
    assert sql.startswith("INSERT INTO market_sources (source_id, adapter, title,")
    assert "ON CONFLICT (source_id) DO UPDATE SET" in sql


def test_translate_serial_insert_returns_id():
    sql, serial = translate("INSERT INTO users (email, name, role, password_hash, active, created_at) VALUES (?, ?, ?, ?, 1, ?)")
    assert serial == "user_id" and sql.endswith("RETURNING user_id")
    assert translate("INSERT OR IGNORE INTO rules (tender_id, rule_id, body) VALUES (?, ?, ?)")[0].endswith("ON CONFLICT DO NOTHING")


def test_row_behaves_like_sqlite_row():
    r = Row(["a", "b"], {"a": 0, "b": 1}, [1, "x"])
    assert r[0] == 1 and r["b"] == "x" and dict(r) == {"a": 1, "b": "x"} and list(r) == [1, "x"]
