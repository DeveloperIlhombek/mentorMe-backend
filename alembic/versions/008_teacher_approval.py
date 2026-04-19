"""008 teacher approval fields

Revision ID: 008_teacher_approval
Revises: 007_syllabus_notifications
Create Date: 2026-04-19

Teacher modeliga is_approved, created_by, created_by_role fieldlari qo'shildi.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '008_teacher_approval'
down_revision = '007_syllabus_notifications'
branch_labels = None
depends_on = None


def _tenant_schemas(conn):
    """Barcha aktiv tenant schemalarini qaytaradi."""
    result = conn.execute(sa.text(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name LIKE 'tenant_%'"
    ))
    return [row[0] for row in result]


def upgrade():
    conn = op.get_bind()
    schemas = _tenant_schemas(conn)

    for schema in schemas:
        # is_approved
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".teachers '
            f'ADD COLUMN IF NOT EXISTS is_approved BOOLEAN NOT NULL DEFAULT FALSE'
        ))
        # created_by
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".teachers '
            f'ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES "{schema}".users(id) ON DELETE SET NULL'
        ))
        # created_by_role
        conn.execute(sa.text(
            f'ALTER TABLE "{schema}".teachers '
            f'ADD COLUMN IF NOT EXISTS created_by_role VARCHAR(20)'
        ))
        # Mavjud teacherlarni approved qilib belgilash (eski ma'lumotlar)
        conn.execute(sa.text(
            f'UPDATE "{schema}".teachers SET is_approved = TRUE WHERE is_approved = FALSE'
        ))


def downgrade():
    conn = op.get_bind()
    schemas = _tenant_schemas(conn)

    for schema in schemas:
        conn.execute(sa.text(f'ALTER TABLE "{schema}".teachers DROP COLUMN IF EXISTS is_approved'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".teachers DROP COLUMN IF EXISTS created_by'))
        conn.execute(sa.text(f'ALTER TABLE "{schema}".teachers DROP COLUMN IF EXISTS created_by_role'))
