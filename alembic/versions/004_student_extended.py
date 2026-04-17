"""
004_student_extended

Yangi maydonlar:
  students.payment_day       — har oyning qaysi kuni to'lov qilinadi (1-31)
  students.monthly_fee       — o'quvchi uchun maxsus to'lov summasi
  students.is_approved       — teacher yaratgan, admin tasdiqlamagan
  students.created_by        — kim yaratdi
  students.pending_delete    — o'chirish tasdiqlash kutilmoqda
  users.telegram_id          — allaqachon bor
  users.telegram_username    — allaqachon bor

Revision ID: 004_student_extended
Revises: 003_trash_finance
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004_student_extended"
down_revision: Union[str, None] = "003_trash_finance"
branch_labels = None
depends_on = None


def _schemas(conn) -> list:
    rows = conn.execute(sa.text(
        "SELECT schema_name FROM public.tenants WHERE is_active = true"
    ))
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()
    for s in _schemas(conn):
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".students
            ADD COLUMN IF NOT EXISTS payment_day    SMALLINT DEFAULT 1
                CHECK (payment_day BETWEEN 1 AND 31),
            ADD COLUMN IF NOT EXISTS monthly_fee    DECIMAL(12,2),
            ADD COLUMN IF NOT EXISTS is_approved    BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS created_by     UUID
                REFERENCES "{s}".users(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS pending_delete BOOLEAN NOT NULL DEFAULT FALSE
        """))


def downgrade() -> None:
    conn = op.get_bind()
    for s in _schemas(conn):
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".students
            DROP COLUMN IF EXISTS payment_day,
            DROP COLUMN IF EXISTS monthly_fee,
            DROP COLUMN IF EXISTS is_approved,
            DROP COLUMN IF EXISTS created_by,
            DROP COLUMN IF EXISTS pending_delete
        """))
