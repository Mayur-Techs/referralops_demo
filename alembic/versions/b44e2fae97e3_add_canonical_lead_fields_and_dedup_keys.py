"""add_canonical_lead_fields_and_dedup_keys

Revision ID: b44e2fae97e3
Revises: 
Create Date: 2026-10-12

Matrix360 Phase B — additive schema changes only.
All new columns are nullable or have a server_default so existing rows
in the current referralops.db are not disturbed.

Does NOT drop any tables. The previous version of this file incorrectly
tried to drop outreach_drafts / outbox_events; those drops are removed
to avoid destroying any data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b44e2fae97e3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Matrix360 canonical fields to leads, partners, and referral_submissions."""

    # ── leads table ─────────────────────────────────────────────────────────
    with op.batch_alter_table('leads', schema=None) as batch_op:
        # Matrix360 canonical fields (all nullable)
        batch_op.add_column(sa.Column('client',           sa.String(80),  nullable=True))
        batch_op.add_column(sa.Column('property_type',    sa.String(40),  nullable=True))
        batch_op.add_column(sa.Column('lead_type',        sa.String(40),  nullable=True))
        batch_op.add_column(sa.Column('source',           sa.String(40),  nullable=True))
        batch_op.add_column(sa.Column('evidence',         sa.Text(),      nullable=True))
        batch_op.add_column(sa.Column('linkedin_url',     sa.String(500), nullable=True))
        batch_op.add_column(sa.Column('owner',            sa.String(120), nullable=True))
        batch_op.add_column(sa.Column('next_action',      sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('next_action_date', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('utm_source',       sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('utm_campaign',     sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('intent',           sa.String(20),  nullable=True))
        batch_op.add_column(sa.Column('stage',            sa.String(40),  nullable=True))
        # opted_out: NOT NULL, defaults FALSE for existing rows via server_default
        batch_op.add_column(sa.Column('opted_out', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        # Deduplication keys (all nullable; populated for new rows)
        batch_op.add_column(sa.Column('dedup_phone',    sa.String(20),  nullable=True))
        batch_op.add_column(sa.Column('dedup_email',    sa.String(254), nullable=True))
        batch_op.add_column(sa.Column('dedup_linkedin', sa.String(500), nullable=True))

        # Make primary_partner_id nullable (it was NOT NULL; existing rows
        # already have valid values so this is safe)
        batch_op.alter_column('primary_partner_id',
                               existing_type=sa.Integer(),
                               nullable=True)

        # Indexes for filtering/deduplication
        batch_op.create_index('ix_leads_client',        ['client'],        unique=False)
        batch_op.create_index('ix_leads_property_type', ['property_type'], unique=False)
        batch_op.create_index('ix_leads_lead_type',     ['lead_type'],     unique=False)
        batch_op.create_index('ix_leads_source',        ['source'],        unique=False)
        batch_op.create_index('ix_leads_intent',        ['intent'],        unique=False)
        batch_op.create_index('ix_leads_stage',         ['stage'],         unique=False)
        batch_op.create_index('ix_leads_owner',         ['owner'],         unique=False)
        batch_op.create_index('ix_leads_dedup_phone',   ['dedup_phone'],   unique=False)
        batch_op.create_index('ix_leads_dedup_email',   ['dedup_email'],   unique=False)
        batch_op.create_index('ix_leads_dedup_linkedin',['dedup_linkedin'],unique=False)

    # ── partners table ───────────────────────────────────────────────────────
    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_approved_broker', sa.Boolean(), nullable=True))

    # ── referral_submissions table ───────────────────────────────────────────
    with op.batch_alter_table('referral_submissions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('duplicate_match_reason', sa.String(80), nullable=True))
        batch_op.alter_column('partner_id',
                               existing_type=sa.Integer(),
                               nullable=True)


def downgrade() -> None:
    """Remove Matrix360 canonical fields (reverses upgrade)."""

    with op.batch_alter_table('referral_submissions', schema=None) as batch_op:
        batch_op.alter_column('partner_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('duplicate_match_reason')

    with op.batch_alter_table('partners', schema=None) as batch_op:
        batch_op.drop_column('is_approved_broker')

    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_index('ix_leads_dedup_linkedin')
        batch_op.drop_index('ix_leads_dedup_email')
        batch_op.drop_index('ix_leads_dedup_phone')
        batch_op.drop_index('ix_leads_owner')
        batch_op.drop_index('ix_leads_stage')
        batch_op.drop_index('ix_leads_intent')
        batch_op.drop_index('ix_leads_source')
        batch_op.drop_index('ix_leads_lead_type')
        batch_op.drop_index('ix_leads_property_type')
        batch_op.drop_index('ix_leads_client')
        batch_op.alter_column('primary_partner_id',
                               existing_type=sa.Integer(),
                               nullable=False)
        batch_op.drop_column('dedup_linkedin')
        batch_op.drop_column('dedup_email')
        batch_op.drop_column('dedup_phone')
        batch_op.drop_column('opted_out')
        batch_op.drop_column('stage')
        batch_op.drop_column('intent')
        batch_op.drop_column('utm_campaign')
        batch_op.drop_column('utm_source')
        batch_op.drop_column('next_action_date')
        batch_op.drop_column('next_action')
        batch_op.drop_column('owner')
        batch_op.drop_column('linkedin_url')
        batch_op.drop_column('evidence')
        batch_op.drop_column('source')
        batch_op.drop_column('lead_type')
        batch_op.drop_column('property_type')
        batch_op.drop_column('client')
