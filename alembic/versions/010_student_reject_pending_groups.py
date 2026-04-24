"""010 student soft-reject + pending_group_ids

Revision ID: 010_reject_pending_groups
Revises: 009_promo_text
Create Date: 2026-04-24

students jadvaliga ikki ustun qo'shiladi:
  - is_rejected  : BOOLEAN DEFAULT FALSE  — teacher yaratgan o'quvchi reject qilinsa
  - pending_group_ids : JSONB DEFAULT '[]'   — tasdiqlanmaguncha kerakli guruh IDlar
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010_reject_pending_groups"
down_revision = "009_promo_text"
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
        # is_rejected ustuni
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".students '
            f'ADD COLUMN IF NOT EXISTS is_rejected BOOLEAN NOT NULL DEFAULT FALSE'
        ))
        # pending_group_ids ustuni (JSONB: guruh UUID ro'yxati)
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".students '
            f"ADD COLUMN IF NOT EXISTS pending_group_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
        ))
        print(f"  ✅ {schema}: students.is_rejected + pending_group_ids qo'shildi")


def downgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)

    for schema in schemas:
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".students DROP COLUMN IF EXISTS is_rejected'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".students DROP COLUMN IF EXISTS pending_group_ids'
        ))
