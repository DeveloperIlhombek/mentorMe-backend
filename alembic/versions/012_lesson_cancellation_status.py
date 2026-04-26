"""
012_lesson_cancellation_status
lesson_cancellations jadvaliga status, reviewed_by, reviewed_at ustunlarini qo'shish.
"""
from alembic import op
import sqlalchemy as sa


revision = "012"
down_revision = "011_att_kpi_progress"
branch_labels = None
depends_on = None


def _schemas(conn) -> list:
    rows = conn.execute(sa.text(
        "SELECT schema_name FROM public.tenants WHERE is_active = true"
    ))
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)
    for s in schemas:
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".lesson_cancellations '
            f"ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending'"
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".lesson_cancellations '
            f"ADD COLUMN IF NOT EXISTS reviewed_by UUID NULL"
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".lesson_cancellations '
            f"ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NULL"
        ))
        # Mavjud yozuvlarni 'approved' deb belgilaymiz (chunki ular allaqachon payment_adjusted=true)
        conn.execute(sa.text(
            f'UPDATE "{s}".lesson_cancellations SET status = \'approved\' WHERE payment_adjusted = true'
        ))


def downgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)
    for s in schemas:
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".lesson_cancellations DROP COLUMN IF EXISTS status'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".lesson_cancellations DROP COLUMN IF EXISTS reviewed_by'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".lesson_cancellations DROP COLUMN IF EXISTS reviewed_at'
        ))
