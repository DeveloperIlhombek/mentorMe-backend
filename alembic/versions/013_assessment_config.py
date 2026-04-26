"""
013_assessment_config
- groups jadvaliga progress_deadline_day, progress_deadline_hour qo'shish
- student_progress jadvaliga is_late, group_id (agar yo'q bo'lsa) qo'shish
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def _schemas(conn):
    rows = conn.execute(sa.text(
        "SELECT schema_name FROM public.tenants WHERE is_active = true"
    ))
    return [r[0] for r in rows]


def upgrade():
    conn = op.get_bind()
    for s in _schemas(conn):
        # Guruhga deadline sozlamalari
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".groups '
            f'ADD COLUMN IF NOT EXISTS progress_deadline_day SMALLINT NOT NULL DEFAULT 25'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".groups '
            f'ADD COLUMN IF NOT EXISTS progress_deadline_hour SMALLINT NOT NULL DEFAULT 23'
        ))
        # student_progress ga is_late
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".student_progress '
            f'ADD COLUMN IF NOT EXISTS is_late BOOLEAN NOT NULL DEFAULT FALSE'
        ))
        # scheduled_date ni nullable qilamiz (endi guruh bo'yicha bulk)
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".student_progress '
            f'ALTER COLUMN scheduled_date DROP NOT NULL'
        ))


def downgrade():
    conn = op.get_bind()
    for s in _schemas(conn):
        conn.execute(sa.text(f'ALTER TABLE "{s}".groups DROP COLUMN IF EXISTS progress_deadline_day'))
        conn.execute(sa.text(f'ALTER TABLE "{s}".groups DROP COLUMN IF EXISTS progress_deadline_hour'))
        conn.execute(sa.text(f'ALTER TABLE "{s}".student_progress DROP COLUMN IF EXISTS is_late'))
