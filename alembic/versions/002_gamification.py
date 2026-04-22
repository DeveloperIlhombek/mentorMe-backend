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


def _create_base_schema(conn, schema: str) -> None:
    """
    Schema va barcha ASOSIY jadvallarni yaratish.
    001_initial.create_tenant_tables() ga ekvivalent — alembic tomonidan
    chaqirilmagan bo'lsa (masalan, DB reset + seed_tenants.py oqimida).
    """
    # Schema o'zini yaratish
    conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # users
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".users (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_id       BIGINT      UNIQUE,
            telegram_username VARCHAR(100),
            email             VARCHAR(200) UNIQUE,
            password_hash     TEXT,
            first_name        VARCHAR(100) NOT NULL,
            last_name         VARCHAR(100),
            phone             VARCHAR(20)  UNIQUE,
            role              VARCHAR(20)  NOT NULL,
            avatar_url        TEXT,
            language_code     VARCHAR(5)   DEFAULT 'uz',
            is_active         BOOLEAN      DEFAULT TRUE,
            is_verified       BOOLEAN      DEFAULT FALSE,
            last_seen_at      TIMESTAMPTZ,
            created_at        TIMESTAMPTZ  DEFAULT NOW(),
            updated_at        TIMESTAMPTZ  DEFAULT NOW()
        )
    """))

    # branches
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".branches (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR(200) NOT NULL,
            address    TEXT,
            phone      VARCHAR(20),
            is_main    BOOLEAN     DEFAULT FALSE,
            is_active  BOOLEAN     DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))

    # teachers
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".teachers (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID        NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE,
            branch_id     UUID        REFERENCES "{schema}".branches(id),
            subjects      TEXT[],
            bio           TEXT,
            salary_type   VARCHAR(20),
            salary_amount DECIMAL(12,2),
            hired_at      DATE,
            is_active     BOOLEAN     DEFAULT TRUE,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            updated_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """))

    # groups
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".groups (
            id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR(200) NOT NULL,
            branch_id   UUID         REFERENCES "{schema}".branches(id),
            teacher_id  UUID         REFERENCES "{schema}".teachers(id),
            subject     VARCHAR(200) NOT NULL,
            level       VARCHAR(50),
            schedule    JSONB,
            start_date  DATE,
            end_date    DATE,
            monthly_fee DECIMAL(12,2),
            max_students INTEGER     DEFAULT 15,
            status      VARCHAR(20)  DEFAULT 'active',
            created_at  TIMESTAMPTZ  DEFAULT NOW(),
            updated_at  TIMESTAMPTZ  DEFAULT NOW()
        )
    """))

    # students
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".students (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID        NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE,
            branch_id     UUID        REFERENCES "{schema}".branches(id),
            date_of_birth DATE,
            gender        VARCHAR(10),
            parent_id     UUID        REFERENCES "{schema}".users(id),
            parent_phone  VARCHAR(20),
            balance       DECIMAL(12,2) DEFAULT 0,
            enrolled_at   DATE        DEFAULT CURRENT_DATE,
            is_active     BOOLEAN     DEFAULT TRUE,
            notes         TEXT,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            updated_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """))

    # student_groups
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".student_groups (
            id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id UUID    NOT NULL REFERENCES "{schema}".students(id) ON DELETE CASCADE,
            group_id   UUID    NOT NULL REFERENCES "{schema}".groups(id) ON DELETE CASCADE,
            joined_at  DATE    DEFAULT CURRENT_DATE,
            left_at    DATE,
            is_active  BOOLEAN DEFAULT TRUE,
            UNIQUE(student_id, group_id)
        )
    """))

    # attendance
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".attendance (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id      UUID        NOT NULL REFERENCES "{schema}".students(id),
            group_id        UUID        NOT NULL REFERENCES "{schema}".groups(id),
            teacher_id      UUID        REFERENCES "{schema}".teachers(id),
            date            DATE        NOT NULL,
            status          VARCHAR(20) NOT NULL,
            arrived_at      TIME,
            note            TEXT,
            parent_notified BOOLEAN     DEFAULT FALSE,
            notified_at     TIMESTAMPTZ,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(student_id, group_id, date)
        )
    """))

    # payments
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".payments (
            id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id           UUID         NOT NULL REFERENCES "{schema}".students(id),
            group_id             UUID         REFERENCES "{schema}".groups(id),
            amount               DECIMAL(12,2) NOT NULL,
            currency             VARCHAR(5)   DEFAULT 'UZS',
            payment_type         VARCHAR(30)  DEFAULT 'subscription',
            payment_method       VARCHAR(30)  DEFAULT 'cash',
            click_transaction_id VARCHAR(200) UNIQUE,
            click_paydoc_id      VARCHAR(200),
            status               VARCHAR(20)  DEFAULT 'completed',
            received_by          UUID         REFERENCES "{schema}".users(id),
            period_month         INTEGER,
            period_year          INTEGER,
            note                 TEXT,
            paid_at              TIMESTAMPTZ,
            created_at           TIMESTAMPTZ  DEFAULT NOW()
        )
    """))

    # gamification_profiles
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".gamification_profiles (
            id                 UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id         UUID    UNIQUE NOT NULL REFERENCES "{schema}".students(id),
            total_xp           INTEGER DEFAULT 0,
            current_level      INTEGER DEFAULT 1,
            current_streak     INTEGER DEFAULT 0,
            max_streak         INTEGER DEFAULT 0,
            last_activity_date DATE,
            weekly_xp          INTEGER DEFAULT 0,
            weekly_reset_at    TIMESTAMPTZ,
            created_at         TIMESTAMPTZ DEFAULT NOW(),
            updated_at         TIMESTAMPTZ DEFAULT NOW()
        )
    """))

    # xp_transactions
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".xp_transactions (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id   UUID        NOT NULL REFERENCES "{schema}".students(id),
            amount       INTEGER     NOT NULL,
            reason       VARCHAR(100) NOT NULL,
            reference_id UUID,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """))

    # Indekslar
    conn.execute(sa.text(
        f'CREATE INDEX IF NOT EXISTS idx_users_telegram_{schema.replace("-","_")} '
        f'ON "{schema}".users(telegram_id)'
    ))
    conn.execute(sa.text(
        f'CREATE INDEX IF NOT EXISTS idx_users_email_{schema.replace("-","_")} '
        f'ON "{schema}".users(email)'
    ))
    conn.execute(sa.text(
        f'CREATE INDEX IF NOT EXISTS idx_att_student_{schema.replace("-","_")} '
        f'ON "{schema}".attendance(student_id, date)'
    ))
    conn.execute(sa.text(
        f'CREATE INDEX IF NOT EXISTS idx_att_group_{schema.replace("-","_")} '
        f'ON "{schema}".attendance(group_id, date)'
    ))
    conn.execute(sa.text(
        f'CREATE INDEX IF NOT EXISTS idx_pay_student_{schema.replace("-","_")} '
        f'ON "{schema}".payments(student_id)'
    ))

    print(f"  ✅ {schema}: base tables created")


def upgrade() -> None:
    conn = op.get_bind()
    schemas = _get_schemas(conn)

    for schema in schemas:
        # ── 1. Schema va asosiy jadvallarni yaratish (agar yo'q bo'lsa) ──
        _create_base_schema(conn, schema)

        # ── 2. Gamification jadvallari ────────────────────────────────
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

        # Default achievements
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

        # Notifications indekslari
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_notif_user_{schema.replace("-","_")}
            ON "{schema}".notifications(user_id)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_notif_unread_{schema.replace("-","_")}
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
