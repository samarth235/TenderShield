"""Table definitions: the single description of the schema.

Alembic migrations (``migrations/versions``) create and evolve these tables; the database layer
reads primary keys and column order from here to translate SQLite-style statements for
PostgreSQL. ``tests/test_migrations.py`` fails if the migrations and this file drift apart.

JSON-shaped values are stored as TEXT (see ``db.JSON_COLUMNS``) so both engines behave the same.
"""

from __future__ import annotations

from sqlalchemy import Column, Float, Index, Integer, MetaData, Table, Text, text

metadata = MetaData()


def _text(name: str, **kw) -> Column:
    return Column(name, Text, **kw)


# --- Tenders, documents and the assurance pipeline ------------------------------------

tenders = Table(
    "tenders", metadata,
    _text("tender_id", primary_key=True),
    _text("title", nullable=False),
    _text("department"),
    Column("estimated_value_cr", Float),
    _text("published_on"),
    _text("bid_deadline"),
    _text("status", nullable=False),
    Column("is_current", Integer, nullable=False, server_default=text("0")),
    _text("source", nullable=False),
    _text("meta", nullable=False, server_default=text("'{}'")),
)

vendors = Table(
    "vendors", metadata,
    _text("vendor_id", primary_key=True),
    _text("alias"),
    _text("name", nullable=False),
    _text("gstin"),
    _text("pan"),
    _text("registered_address"),
    _text("phone"),
    _text("email"),
    _text("incorporated"),
    Column("msme", Integer, nullable=False, server_default=text("0")),
    _text("directors"),
    _text("meta", nullable=False, server_default=text("'{}'")),
)

bids = Table(
    "bids", metadata,
    Column("bid_id", Integer, primary_key=True, autoincrement=True),
    _text("tender_id", nullable=False),
    _text("vendor_id"),
    _text("bidder_name", nullable=False),
    _text("bidder_gstin"),
    Column("amount_cr", Float),
    _text("submitted_at"),
    _text("outcome", nullable=False),
    Column("rank", Integer),
)
Index("idx_bids_tender", bids.c.tender_id)

documents = Table(
    "documents", metadata,
    _text("document_id", primary_key=True),
    _text("tender_id", nullable=False),
    _text("vendor_id"),
    _text("kind", nullable=False),
    _text("filename", nullable=False),
    _text("path", nullable=False),
    _text("sha256", nullable=False),
    Column("pages", Integer, nullable=False, server_default=text("0")),
    _text("meta", nullable=False, server_default=text("'{}'")),
)

document_pages = Table(
    "document_pages", metadata,
    _text("document_id", primary_key=True),
    Column("page", Integer, primary_key=True),
    _text("text", nullable=False),
)

vendor_facts = Table(
    "vendor_facts", metadata,
    _text("tender_id", primary_key=True),
    _text("vendor_id", primary_key=True),
    _text("metric", primary_key=True),
    _text("value", nullable=False),
    _text("document_id"),
    Column("page", Integer),
    _text("excerpt"),
)

rules = Table(
    "rules", metadata,
    _text("tender_id", primary_key=True),
    _text("rule_id", primary_key=True),
    _text("body", nullable=False),
)

compliance = Table(
    "compliance", metadata,
    _text("tender_id", primary_key=True),
    _text("vendor_id", primary_key=True),
    _text("rule_id", primary_key=True),
    _text("result", nullable=False),
    _text("body", nullable=False),
)

artifacts = Table(
    "artifacts", metadata,
    _text("tender_id", primary_key=True),
    _text("stage", primary_key=True),
    _text("body", nullable=False),
    _text("created_at", nullable=False),
)

findings = Table(
    "findings", metadata,
    _text("finding_id", primary_key=True),
    _text("tender_id", nullable=False),
    _text("category", nullable=False),
    _text("level", nullable=False),
    _text("status", nullable=False),
    _text("body", nullable=False),
)

counterfactual_runs = Table(
    "counterfactual_runs", metadata,
    Column("run_id", Integer, primary_key=True, autoincrement=True),
    _text("finding_id", nullable=False),
    _text("removed", nullable=False),
    _text("run_result", nullable=False),
    _text("created_at", nullable=False),
)

audit_log = Table(
    "audit_log", metadata,
    Column("entry_id", Integer, primary_key=True, autoincrement=True),
    _text("tender_id", nullable=False),
    _text("finding_id"),
    _text("action", nullable=False),
    _text("actor", nullable=False),
    _text("payload", nullable=False),
    _text("created_at", nullable=False),
    _text("prev_hash", nullable=False),
    _text("entry_hash", nullable=False),
)
Index("idx_audit_tender", audit_log.c.tender_id)

users = Table(
    "users", metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=True),
    _text("email", nullable=False, unique=True),
    _text("name", nullable=False, server_default=text("''")),
    _text("role", nullable=False),
    _text("password_hash", nullable=False),
    Column("active", Integer, nullable=False, server_default=text("1")),
    _text("created_at", nullable=False),
)

snapshots = Table(
    "snapshots", metadata,
    _text("snapshot_id", primary_key=True),
    _text("tender_id", nullable=False),
    _text("created_at", nullable=False),
    _text("bundle", nullable=False),
    _text("bundle_hash", nullable=False),
    Column("audit_head", Integer, nullable=False),
)

# --- Market intelligence (real published award / bid data) ---------------------------

market_sources = Table(
    "market_sources", metadata,
    _text("source_id", primary_key=True),
    _text("adapter", nullable=False),
    _text("title", nullable=False),
    _text("origin_url"),
    _text("licence"),
    _text("country_scope"),
    _text("file_sha256"),
    Column("rows_awards", Integer, nullable=False, server_default=text("0")),
    Column("rows_bids", Integer, nullable=False, server_default=text("0")),
    _text("imported_at", nullable=False),
    _text("notes"),
)

market_awards = Table(
    "market_awards", metadata,
    _text("award_id", primary_key=True),
    _text("source_id", nullable=False),
    _text("tender_ref"),
    _text("lot_ref"),
    _text("project_id"),
    _text("buyer"),
    _text("title"),
    _text("description"),
    _text("cpv"),
    _text("capability", nullable=False),
    _text("capability_basis", nullable=False),
    _text("category"),
    _text("method"),
    _text("country"),
    _text("region"),
    _text("signed_on"),
    _text("supplier_key", nullable=False),
    _text("supplier_name", nullable=False),
    _text("supplier_country"),
    Column("amount", Float),
    _text("currency"),
    Column("amount_inr_cr", Float),
    Column("n_bidders", Integer),
)
Index("idx_awards_supplier", market_awards.c.supplier_key)
Index("idx_awards_capability", market_awards.c.capability)
Index("idx_awards_source", market_awards.c.source_id)

market_bids = Table(
    "market_bids", metadata,
    Column("bid_id", Integer, primary_key=True, autoincrement=True),
    _text("source_id", nullable=False),
    _text("tender_ref", nullable=False),
    _text("lot_ref"),
    _text("supplier_key", nullable=False),
    _text("supplier_name", nullable=False),
    Column("amount", Float),
    _text("currency"),
    Column("won", Integer),
    Column("rank", Integer),
    _text("bid_date"),
    _text("capability"),
)
Index("idx_mbids_tender", market_bids.c.tender_ref, market_bids.c.lot_ref)
Index("idx_mbids_supplier", market_bids.c.supplier_key)

market_suppliers = Table(
    "market_suppliers", metadata,
    _text("supplier_key", primary_key=True),
    _text("name", nullable=False),
    _text("country"),
    _text("sources", nullable=False),
    Column("n_awards", Integer, nullable=False),
    Column("total_inr_cr", Float),
    Column("max_inr_cr", Float),
    Column("median_inr_cr", Float),
    _text("first_award"),
    _text("last_award"),
    _text("capabilities", nullable=False),
    _text("capability_values", nullable=False),
    Column("n_bids", Integer, nullable=False, server_default=text("0")),
    _text("msme_status", nullable=False, server_default=text("'UNKNOWN'")),
    _text("msme_evidence"),
    _text("identifiers", nullable=False, server_default=text("'{}'")),
)
Index("idx_suppliers_name", market_suppliers.c.name)

MARKET_TABLES = [market_sources, market_awards, market_bids, market_suppliers]
CORE_TABLES = [t for t in metadata.sorted_tables if t not in MARKET_TABLES]
