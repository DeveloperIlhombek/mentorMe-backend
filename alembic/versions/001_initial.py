"""initial: public schema + tenant tables

Revision ID: 001_initial
Revises:
Create Date: 2026-03-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. public.subscription_plans ──────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS public")

    op.create_table(
        "subscription_plans",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name",          sa.String(50),  nullable=False),
        sa.Column("slug",          sa.String(30),  nullable=False, unique=True),
        sa.Column("price_monthly", sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("max_students",  sa.Integer(),   nullable=True),
        sa.Column("max_teachers",  sa.Integer(),   nullable=True),
        sa.Column("max_branches",  sa.Integer(),   server_default="1"),
        sa.Column("features",      postgresql.JSONB(), server_default="{}"),
        sa.Column("is_active",     sa.Boolean(),   server_default="true"),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema="public",
    )

    # ── 2. public.tenants ──────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug",                sa.String(50),  nullable=False, unique=True),
        sa.Column("name",                sa.String(200), nullable=False),
        sa.Column("schema_name",         sa.String(60),  nullable=False, unique=True),
        sa.Column("owner_telegram_id",   sa.BigInteger(), nullable=True),
        sa.Column("phone",               sa.String(20),  nullable=True),
        sa.Column("address",             sa.Text(),      nullable=True),
        sa.Column("logo_url",            sa.Text(),      nullable=True),
        sa.Column("plan_id",             postgresql.UUID(as_uuid=True), sa.ForeignKey("public.subscription_plans.id"), nullable=True),
        sa.Column("subscription_status", sa.String(20),  server_default="trial"),
        sa.Column("trial_ends_at",       sa.DateTime(timezone=True), nullable=True),
        sa.Column("click_merchant_id",   sa.String(100), nullable=True),
        sa.Column("click_service_id",    sa.String(100), nullable=True),
        sa.Column("bot_token",           sa.Text(),      nullable=True),
        sa.Column("bot_username",        sa.String(100), nullable=True),
        sa.Column("custom_domain",       sa.String(200), nullable=True),
        sa.Column("brand_color",         sa.String(7),   server_default="'#3B82F6'"),
        sa.Column("is_active",           sa.Boolean(),   server_default="true"),
        sa.Column("created_at",          sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema="public",
    )


def create_tenant_tables(schema: str) -> None:
    """
    Bu funksiya har bir yangi tenant uchun chaqiriladi.
    Odatda seed.py yoki tenant yaratish servisi chaqiradi.
    """
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

    # users
    op.execute(f"""
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
    """)

    # branches
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".branches (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR(200) NOT NULL,
            address    TEXT,
            phone      VARCHAR(20),
            is_main    BOOLEAN     DEFAULT FALSE,
            is_active  BOOLEAN     DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # teachers
    op.execute(f"""
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
    """)

    # groups
    op.execute(f"""
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
    """)

    # students
    op.execute(f"""
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
    """)

    # student_groups
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".student_groups (
            id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id UUID    NOT NULL REFERENCES "{schema}".students(id) ON DELETE CASCADE,
            group_id   UUID    NOT NULL REFERENCES "{schema}".groups(id) ON DELETE CASCADE,
            joined_at  DATE    DEFAULT CURRENT_DATE,
            left_at    DATE,
            is_active  BOOLEAN DEFAULT TRUE,
            UNIQUE(student_id, group_id)
        )
    """)

    # attendance
    op.execute(f"""
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
    """)

    # payments
    op.execute(f"""
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
    """)

    # gamification_profiles
    op.execute(f"""
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
    """)

    # xp_transactions
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".xp_transactions (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id   UUID        NOT NULL REFERENCES "{schema}".students(id),
            amount       INTEGER     NOT NULL,
            reason       VARCHAR(100) NOT NULL,
            reference_id UUID,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # achievements
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".achievements (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            slug            VARCHAR(50) UNIQUE NOT NULL,
            name_uz         VARCHAR(100) NOT NULL,
            name_ru         VARCHAR(100),
            description_uz  TEXT,
            icon            VARCHAR(10),
            xp_reward       INTEGER     DEFAULT 0,
            condition_type  VARCHAR(50) NOT NULL,
            condition_value INTEGER     NOT NULL,
            is_active       BOOLEAN     DEFAULT TRUE
        )
    """)

    # student_achievements
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".student_achievements (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id     UUID        NOT NULL REFERENCES "{schema}".students(id),
            achievement_id UUID        NOT NULL REFERENCES "{schema}".achievements(id),
            earned_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(student_id, achievement_id)
        )
    """)

    # notifications
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".notifications (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID        NOT NULL REFERENCES "{schema}".users(id),
            type       VARCHAR(50) NOT NULL,
            title      VARCHAR(200) NOT NULL,
            body       TEXT        NOT NULL,
            data       JSONB       DEFAULT '{{}}',
            channel    VARCHAR(20) DEFAULT 'telegram',
            is_read    BOOLEAN     DEFAULT FALSE,
            sent_at    TIMESTAMPTZ,
            read_at    TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Indekslar
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_users_telegram ON "{schema}".users(telegram_id)')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_users_email ON "{schema}".users(email)')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_att_student_date ON "{schema}".attendance(student_id, date)')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_att_group_date ON "{schema}".attendance(group_id, date)')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_pay_student ON "{schema}".payments(student_id)')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_xp_student ON "{schema}".xp_transactions(student_id)')
    op.execute(f'CREATE INDEX IF NOT EXISTS idx_gam_weekly ON "{schema}".gamification_profiles(weekly_xp DESC)')


def downgrade() -> None:
    op.drop_table("tenants",            schema="public")
    op.drop_table("subscription_plans", schema="public")
