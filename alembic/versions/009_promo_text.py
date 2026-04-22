"""009 add promo_text to invitations

Revision ID: 009_promo_text
Revises: 008_teacher_approval
Create Date: 2026-04-22

invitations jadvaliga promo_text (TEXT, nullable) ustuni qo'shiladi.
Model bilan DB sinhronlashtiriladi.
"""
from alembic import op
import sqlalchemy as sa

revision = "009_promo_text"
down_revision = "008_teacher_approval"
branch_labels = None
depends_on = None


def _schemas(conn) -> list:
    rows = conn.execute(
        sa.text("SELECT schema_name FROM public.tenants WHERE is_active = true")
    )
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)

    for schema in schemas:
        # invitations.promo_text
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".invitations '
            f'ADD COLUMN IF NOT EXISTS promo_text TEXT'
        ))
        print(f"  ✅ {schema}: invitations.promo_text qo'shildi")


def downgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)

    for schema in schemas:
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".invitations '
            f'DROP COLUMN IF EXISTS promo_text'
        ))
