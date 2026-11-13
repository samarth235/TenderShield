"""Initial schema: tenders, assurance pipeline, users, audit trail and market intelligence.

`if_not_exists` lets databases created before migrations existed (hackathon SQLite files)
adopt this revision without losing data.

Revision ID: 0001
Revises:
Create Date: 2026-11-12 14:45:00.501824
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('artifacts',
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('stage', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('tender_id', 'stage'),
    if_not_exists=True,
    )
    op.create_table('audit_log',
    sa.Column('entry_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('finding_id', sa.Text(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('actor', sa.Text(), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('prev_hash', sa.Text(), nullable=False),
    sa.Column('entry_hash', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('entry_id'),
    if_not_exists=True,
    )
    op.create_index('idx_audit_tender', 'audit_log', ['tender_id'], unique=False, if_not_exists=True)

    op.create_table('bids',
    sa.Column('bid_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('vendor_id', sa.Text(), nullable=True),
    sa.Column('bidder_name', sa.Text(), nullable=False),
    sa.Column('bidder_gstin', sa.Text(), nullable=True),
    sa.Column('amount_cr', sa.Float(), nullable=True),
    sa.Column('submitted_at', sa.Text(), nullable=True),
    sa.Column('outcome', sa.Text(), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('bid_id'),
    if_not_exists=True,
    )
    op.create_index('idx_bids_tender', 'bids', ['tender_id'], unique=False, if_not_exists=True)

    op.create_table('compliance',
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('vendor_id', sa.Text(), nullable=False),
    sa.Column('rule_id', sa.Text(), nullable=False),
    sa.Column('result', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('tender_id', 'vendor_id', 'rule_id'),
    if_not_exists=True,
    )
    op.create_table('counterfactual_runs',
    sa.Column('run_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('finding_id', sa.Text(), nullable=False),
    sa.Column('removed', sa.Text(), nullable=False),
    sa.Column('run_result', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('run_id'),
    if_not_exists=True,
    )
    op.create_table('document_pages',
    sa.Column('document_id', sa.Text(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('document_id', 'page'),
    if_not_exists=True,
    )
    op.create_table('documents',
    sa.Column('document_id', sa.Text(), nullable=False),
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('vendor_id', sa.Text(), nullable=True),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('filename', sa.Text(), nullable=False),
    sa.Column('path', sa.Text(), nullable=False),
    sa.Column('sha256', sa.Text(), nullable=False),
    sa.Column('pages', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('meta', sa.Text(), server_default=sa.text("'{}'"), nullable=False),
    sa.PrimaryKeyConstraint('document_id'),
    if_not_exists=True,
    )
    op.create_table('findings',
    sa.Column('finding_id', sa.Text(), nullable=False),
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('category', sa.Text(), nullable=False),
    sa.Column('level', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('finding_id'),
    if_not_exists=True,
    )
    op.create_table('market_awards',
    sa.Column('award_id', sa.Text(), nullable=False),
    sa.Column('source_id', sa.Text(), nullable=False),
    sa.Column('tender_ref', sa.Text(), nullable=True),
    sa.Column('lot_ref', sa.Text(), nullable=True),
    sa.Column('project_id', sa.Text(), nullable=True),
    sa.Column('buyer', sa.Text(), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('cpv', sa.Text(), nullable=True),
    sa.Column('capability', sa.Text(), nullable=False),
    sa.Column('capability_basis', sa.Text(), nullable=False),
    sa.Column('category', sa.Text(), nullable=True),
    sa.Column('method', sa.Text(), nullable=True),
    sa.Column('country', sa.Text(), nullable=True),
    sa.Column('region', sa.Text(), nullable=True),
    sa.Column('signed_on', sa.Text(), nullable=True),
    sa.Column('supplier_key', sa.Text(), nullable=False),
    sa.Column('supplier_name', sa.Text(), nullable=False),
    sa.Column('supplier_country', sa.Text(), nullable=True),
    sa.Column('amount', sa.Float(), nullable=True),
    sa.Column('currency', sa.Text(), nullable=True),
    sa.Column('amount_inr_cr', sa.Float(), nullable=True),
    sa.Column('n_bidders', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('award_id'),
    if_not_exists=True,
    )
    op.create_index('idx_awards_capability', 'market_awards', ['capability'], unique=False, if_not_exists=True)
    op.create_index('idx_awards_source', 'market_awards', ['source_id'], unique=False, if_not_exists=True)
    op.create_index('idx_awards_supplier', 'market_awards', ['supplier_key'], unique=False, if_not_exists=True)

    op.create_table('market_bids',
    sa.Column('bid_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('source_id', sa.Text(), nullable=False),
    sa.Column('tender_ref', sa.Text(), nullable=False),
    sa.Column('lot_ref', sa.Text(), nullable=True),
    sa.Column('supplier_key', sa.Text(), nullable=False),
    sa.Column('supplier_name', sa.Text(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=True),
    sa.Column('currency', sa.Text(), nullable=True),
    sa.Column('won', sa.Integer(), nullable=True),
    sa.Column('rank', sa.Integer(), nullable=True),
    sa.Column('bid_date', sa.Text(), nullable=True),
    sa.Column('capability', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('bid_id'),
    if_not_exists=True,
    )
    op.create_index('idx_mbids_supplier', 'market_bids', ['supplier_key'], unique=False, if_not_exists=True)
    op.create_index('idx_mbids_tender', 'market_bids', ['tender_ref', 'lot_ref'], unique=False, if_not_exists=True)

    op.create_table('market_sources',
    sa.Column('source_id', sa.Text(), nullable=False),
    sa.Column('adapter', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('origin_url', sa.Text(), nullable=True),
    sa.Column('licence', sa.Text(), nullable=True),
    sa.Column('country_scope', sa.Text(), nullable=True),
    sa.Column('file_sha256', sa.Text(), nullable=True),
    sa.Column('rows_awards', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('rows_bids', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('imported_at', sa.Text(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('source_id'),
    if_not_exists=True,
    )
    op.create_table('market_suppliers',
    sa.Column('supplier_key', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('country', sa.Text(), nullable=True),
    sa.Column('sources', sa.Text(), nullable=False),
    sa.Column('n_awards', sa.Integer(), nullable=False),
    sa.Column('total_inr_cr', sa.Float(), nullable=True),
    sa.Column('max_inr_cr', sa.Float(), nullable=True),
    sa.Column('median_inr_cr', sa.Float(), nullable=True),
    sa.Column('first_award', sa.Text(), nullable=True),
    sa.Column('last_award', sa.Text(), nullable=True),
    sa.Column('capabilities', sa.Text(), nullable=False),
    sa.Column('capability_values', sa.Text(), nullable=False),
    sa.Column('n_bids', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('msme_status', sa.Text(), server_default=sa.text("'UNKNOWN'"), nullable=False),
    sa.Column('msme_evidence', sa.Text(), nullable=True),
    sa.Column('identifiers', sa.Text(), server_default=sa.text("'{}'"), nullable=False),
    sa.PrimaryKeyConstraint('supplier_key'),
    if_not_exists=True,
    )
    op.create_index('idx_suppliers_name', 'market_suppliers', ['name'], unique=False, if_not_exists=True)

    op.create_table('rules',
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('rule_id', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('tender_id', 'rule_id'),
    if_not_exists=True,
    )
    op.create_table('snapshots',
    sa.Column('snapshot_id', sa.Text(), nullable=False),
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('bundle', sa.Text(), nullable=False),
    sa.Column('bundle_hash', sa.Text(), nullable=False),
    sa.Column('audit_head', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('snapshot_id'),
    if_not_exists=True,
    )
    op.create_table('tenders',
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('department', sa.Text(), nullable=True),
    sa.Column('estimated_value_cr', sa.Float(), nullable=True),
    sa.Column('published_on', sa.Text(), nullable=True),
    sa.Column('bid_deadline', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('is_current', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('meta', sa.Text(), server_default=sa.text("'{}'"), nullable=False),
    sa.PrimaryKeyConstraint('tender_id'),
    if_not_exists=True,
    )
    op.create_table('users',
    sa.Column('user_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('active', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('email'),
    if_not_exists=True,
    )
    op.create_table('vendor_facts',
    sa.Column('tender_id', sa.Text(), nullable=False),
    sa.Column('vendor_id', sa.Text(), nullable=False),
    sa.Column('metric', sa.Text(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('document_id', sa.Text(), nullable=True),
    sa.Column('page', sa.Integer(), nullable=True),
    sa.Column('excerpt', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('tender_id', 'vendor_id', 'metric'),
    if_not_exists=True,
    )
    op.create_table('vendors',
    sa.Column('vendor_id', sa.Text(), nullable=False),
    sa.Column('alias', sa.Text(), nullable=True),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('gstin', sa.Text(), nullable=True),
    sa.Column('pan', sa.Text(), nullable=True),
    sa.Column('registered_address', sa.Text(), nullable=True),
    sa.Column('phone', sa.Text(), nullable=True),
    sa.Column('email', sa.Text(), nullable=True),
    sa.Column('incorporated', sa.Text(), nullable=True),
    sa.Column('msme', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('directors', sa.Text(), nullable=True),
    sa.Column('meta', sa.Text(), server_default=sa.text("'{}'"), nullable=False),
    sa.PrimaryKeyConstraint('vendor_id'),
    if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table('vendors')
    op.drop_table('vendor_facts')
    op.drop_table('users')
    op.drop_table('tenders')
    op.drop_table('snapshots')
    op.drop_table('rules')
    op.drop_index('idx_suppliers_name', table_name='market_suppliers')

    op.drop_table('market_suppliers')
    op.drop_table('market_sources')
    op.drop_index('idx_mbids_tender', table_name='market_bids')
    op.drop_index('idx_mbids_supplier', table_name='market_bids')

    op.drop_table('market_bids')
    op.drop_index('idx_awards_supplier', table_name='market_awards')
    op.drop_index('idx_awards_source', table_name='market_awards')
    op.drop_index('idx_awards_capability', table_name='market_awards')

    op.drop_table('market_awards')
    op.drop_table('findings')
    op.drop_table('documents')
    op.drop_table('document_pages')
    op.drop_table('counterfactual_runs')
    op.drop_table('compliance')
    op.drop_index('idx_bids_tender', table_name='bids')

    op.drop_table('bids')
    op.drop_index('idx_audit_tender', table_name='audit_log')

    op.drop_table('audit_log')
    op.drop_table('artifacts')
