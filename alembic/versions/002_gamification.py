"""add gamification, notifications, achievements to tenant schema

Revision ID: 002_gamification
Revises: 001_initial
Create Date: 2026-03-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_gamification"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_schemas(conn) -> list:
    """Barcha tenant schemalarini olish."""
    result = conn.execute(
        sa.text("SELECT schema_name FROM public.tenants WHERE is_active = true")
    )
    return [row[0] for row in result]


def upgrade() -> None:
    conn = op.get_bind()
    schemas = _get_schemas(conn)

    for schema in schemas:
        # Jadvallar mavjud bo'lsa o'tkazib yuborish
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".achievements (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug            VARCHAR(50) NOT NULL UNIQUE,
                name_uz         VARCHAR(100) NOT NULL,
                name_ru         VARCHAR(100),
                description_uz  TEXT,
                icon            VARCHAR(10),
                xp_reward       INTEGER DEFAULT 0,
                condition_type  VARCHAR(50) NOT NULL,
                condition_value INTEGER NOT NULL,
                is_active       BOOLEAN DEFAULT TRUE
            )
        """))

        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".student_achievements (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id     UUID NOT NULL REFERENCES "{schema}".students(id),
                achievement_id UUID NOT NULL REFERENCES "{schema}".achievements(id),
                earned_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(student_id, achievement_id)
            )
        """))

        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".notifications (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id     UUID NOT NULL REFERENCES "{schema}".users(id),
                type        VARCHAR(50) NOT NULL,
                title       VARCHAR(200) NOT NULL,
                body        TEXT NOT NULL,
                data        JSONB DEFAULT '{{}}',
                channel     VARCHAR(20) DEFAULT 'telegram',
                is_read     BOOLEAN DEFAULT FALSE,
                sent_at     TIMESTAMPTZ,
                read_at     TIMESTAMPTZ,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # Default achievements qo'shish
        conn.execute(sa.text(f"""
            INSERT INTO "{schema}".achievements
                (slug, name_uz, name_ru, icon, xp_reward, condition_type, condition_value)
            VALUES
                ('streak_7',    '7 kunlik streak',   '7-дневный стрик',   '🔥', 100, 'streak', 7),
                ('streak_30',   '30 kunlik streak',  '30-дневный стрик',  '💎', 500, 'streak', 30),
                ('xp_100',      '100 XP',            '100 XP',            '⭐', 0,   'xp',     100),
                ('xp_1000',     '1000 XP',           '1000 XP',           '🏆', 50,  'xp',     1000),
                ('xp_5000',     '5000 XP',           '5000 XP',           '👑', 200, 'xp',     5000),
                ('first_lesson','Birinchi dars',     'Первый урок',       '📚', 20,  'xp',     20)
            ON CONFLICT (slug) DO NOTHING
        """))

    # Index qo'shish
    for schema in schemas:
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_notifications_user
            ON "{schema}".notifications(user_id)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_notifications_unread
            ON "{schema}".notifications(user_id, is_read)
            WHERE is_read = FALSE
        """))


def downgrade() -> None:
    conn = op.get_bind()
    schemas = _get_schemas(conn)
    for schema in schemas:
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".student_achievements'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".achievements'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".notifications'))
