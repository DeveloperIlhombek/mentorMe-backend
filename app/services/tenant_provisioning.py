"""
app/services/tenant_provisioning.py

Yangi tenant uchun PostgreSQL schema, jadvallar va admin foydalanuvchini yaratish.
Migrations 001-014 ni schema-per-tenant DDL ga jamlovchi. Idempotent.
"""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password


# Asosiy tenant jadvallari (barcha 008-014 migration ustunlari bilan)
_TENANT_TABLES_SQL = [
    # users
    """
    CREATE TABLE IF NOT EXISTS "{schema}".users (
        id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        telegram_id              BIGINT UNIQUE,
        telegram_username        VARCHAR(100),
        email                    VARCHAR(200) UNIQUE,
        password_hash            TEXT,
        first_name               VARCHAR(100) NOT NULL,
        last_name                VARCHAR(100),
        phone                    VARCHAR(20) UNIQUE,
        role                     VARCHAR(20) NOT NULL DEFAULT 'student',
        branch_id                UUID,
        avatar_url               TEXT,
        language_code            VARCHAR(5)  DEFAULT 'uz',
        is_active                BOOLEAN     DEFAULT TRUE,
        is_verified              BOOLEAN     DEFAULT FALSE,
        last_seen_at             TIMESTAMPTZ,
        telegram_link_token      VARCHAR(64) UNIQUE,
        telegram_link_expires_at TIMESTAMPTZ,
        telegram_linked_at       TIMESTAMPTZ,
        created_at               TIMESTAMPTZ DEFAULT NOW(),
        updated_at               TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    # user_roles (015) — multi-role: bitta user bir nechta rolda
    """
    CREATE TABLE IF NOT EXISTS "{schema}".user_roles (
        user_id    UUID NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE,
        role       VARCHAR(20) NOT NULL,
        branch_id  UUID NULL,
        is_active  BOOLEAN NOT NULL DEFAULT TRUE,
        granted_by UUID NULL,
        granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, role)
    )
    """,
    # branches
    """
    CREATE TABLE IF NOT EXISTS "{schema}".branches (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name       VARCHAR(200) NOT NULL,
        address    TEXT,
        phone      VARCHAR(20),
        is_main    BOOLEAN DEFAULT FALSE,
        is_active  BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    # teachers
    """
    CREATE TABLE IF NOT EXISTS "{schema}".teachers (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id         UUID NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE,
        branch_id       UUID REFERENCES "{schema}".branches(id),
        subjects        TEXT[]       DEFAULT '{{}}',
        bio             TEXT,
        salary_type     VARCHAR(20)  DEFAULT 'fixed',
        salary_amount   DECIMAL(12,2) DEFAULT 0,
        hired_at        DATE,
        is_active       BOOLEAN      DEFAULT TRUE,
        is_approved     BOOLEAN      DEFAULT TRUE,
        created_by      UUID,
        created_by_role VARCHAR(20),
        created_at      TIMESTAMPTZ  DEFAULT NOW(),
        updated_at      TIMESTAMPTZ  DEFAULT NOW()
    )
    """,
    # groups
    """
    CREATE TABLE IF NOT EXISTS "{schema}".groups (
        id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name                       VARCHAR(200) NOT NULL,
        branch_id                  UUID REFERENCES "{schema}".branches(id),
        teacher_id                 UUID REFERENCES "{schema}".teachers(id),
        subject                    VARCHAR(200) NOT NULL,
        level                      VARCHAR(50),
        schedule                   JSONB DEFAULT '[]',
        start_date                 DATE,
        end_date                   DATE,
        monthly_fee                DECIMAL(12,2) DEFAULT 0,
        max_students               INTEGER DEFAULT 15,
        status                     VARCHAR(20) DEFAULT 'active',
        attendance_deadline_hours  SMALLINT NOT NULL DEFAULT 2,
        progress_deadline_day      SMALLINT NOT NULL DEFAULT 25,
        progress_deadline_hour     SMALLINT NOT NULL DEFAULT 23,
        created_at                 TIMESTAMPTZ DEFAULT NOW(),
        updated_at                 TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    # students
    """
    CREATE TABLE IF NOT EXISTS "{schema}".students (
        id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id                UUID NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE,
        branch_id              UUID REFERENCES "{schema}".branches(id),
        date_of_birth          DATE,
        gender                 VARCHAR(10),
        parent_id              UUID REFERENCES "{schema}".users(id),
        parent_phone           VARCHAR(20),
        balance                DECIMAL(12,2) DEFAULT 0,
        enrolled_at            DATE DEFAULT CURRENT_DATE,
        is_active              BOOLEAN DEFAULT TRUE,
        is_approved            BOOLEAN DEFAULT TRUE,
        is_rejected            BOOLEAN NOT NULL DEFAULT FALSE,
        pending_delete         BOOLEAN DEFAULT FALSE,
        pending_group_ids      JSONB NOT NULL DEFAULT '[]'::jsonb,
        payment_day            INTEGER,
        monthly_fee            DECIMAL(12,2),
        created_by             UUID,
        notes                  TEXT,
        referral_source        VARCHAR(30) NULL,
        referred_by_teacher_id UUID NULL,
        leave_reason           VARCHAR(50) NULL,
        churn_teacher_id       UUID NULL,
        progress_dates         JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at             TIMESTAMPTZ DEFAULT NOW(),
        updated_at             TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    # student_groups
    """
    CREATE TABLE IF NOT EXISTS "{schema}".student_groups (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id UUID NOT NULL REFERENCES "{schema}".students(id) ON DELETE CASCADE,
        group_id   UUID NOT NULL REFERENCES "{schema}".groups(id)   ON DELETE CASCADE,
        joined_at  DATE DEFAULT CURRENT_DATE,
        left_at    DATE,
        is_active  BOOLEAN DEFAULT TRUE,
        UNIQUE(student_id, group_id)
    )
    """,
    # attendance
    """
    CREATE TABLE IF NOT EXISTS "{schema}".attendance (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id      UUID NOT NULL REFERENCES "{schema}".students(id),
        group_id        UUID NOT NULL REFERENCES "{schema}".groups(id),
        teacher_id      UUID REFERENCES "{schema}".teachers(id),
        date            DATE NOT NULL,
        status          VARCHAR(20) DEFAULT 'present',
        arrived_at      TIME,
        note            TEXT,
        parent_notified BOOLEAN DEFAULT FALSE,
        notified_at     TIMESTAMPTZ,
        submitted_at    TIMESTAMPTZ NULL,
        is_late_entry   BOOLEAN NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(student_id, group_id, date)
    )
    """,
    # payments
    """
    CREATE TABLE IF NOT EXISTS "{schema}".payments (
        id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id           UUID NOT NULL REFERENCES "{schema}".students(id),
        group_id             UUID REFERENCES "{schema}".groups(id),
        amount               DECIMAL(12,2) NOT NULL,
        currency             VARCHAR(5)  DEFAULT 'UZS',
        payment_type         VARCHAR(30) DEFAULT 'subscription',
        payment_method       VARCHAR(30) DEFAULT 'cash',
        click_transaction_id VARCHAR(200) UNIQUE,
        click_paydoc_id      VARCHAR(200),
        status               VARCHAR(20) DEFAULT 'completed',
        received_by          UUID REFERENCES "{schema}".users(id),
        period_month         INTEGER,
        period_year          INTEGER,
        note                 TEXT,
        paid_at              TIMESTAMPTZ DEFAULT NOW(),
        created_at           TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    # gamification_profiles
    """
    CREATE TABLE IF NOT EXISTS "{schema}".gamification_profiles (
        id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id         UUID UNIQUE NOT NULL REFERENCES "{schema}".students(id),
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
    """,
    # notifications (014 fields included)
    """
    CREATE TABLE IF NOT EXISTS "{schema}".notifications (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id      UUID NOT NULL REFERENCES "{schema}".users(id),
        type         VARCHAR(50),
        title        VARCHAR(200),
        body         TEXT NOT NULL,
        data         JSONB DEFAULT '{{}}',
        channel      VARCHAR(20) DEFAULT 'telegram',
        is_read      BOOLEAN DEFAULT FALSE,
        sent_at      TIMESTAMPTZ,
        read_at      TIMESTAMPTZ,
        category     VARCHAR(30) NOT NULL DEFAULT 'system',
        priority     VARCHAR(15) NOT NULL DEFAULT 'normal',
        status       VARCHAR(15) NOT NULL DEFAULT 'queued',
        error        TEXT,
        attempts     INTEGER DEFAULT 0,
        dedupe_key   VARCHAR(120),
        scheduled_at TIMESTAMPTZ,
        created_at   TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    # notification_preferences (014)
    """
    CREATE TABLE IF NOT EXISTS "{schema}".notification_preferences (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id             UUID NOT NULL UNIQUE REFERENCES "{schema}".users(id) ON DELETE CASCADE,
        telegram_enabled    BOOLEAN DEFAULT TRUE,
        in_app_enabled      BOOLEAN DEFAULT TRUE,
        disabled_categories VARCHAR(30)[] DEFAULT '{{}}',
        quiet_hours_start   TIME DEFAULT '22:00',
        quiet_hours_end     TIME DEFAULT '07:00',
        timezone            VARCHAR(40) DEFAULT 'Asia/Tashkent',
        created_at          TIMESTAMPTZ DEFAULT NOW(),
        updated_at          TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    # broadcast_jobs (014)
    """
    CREATE TABLE IF NOT EXISTS "{schema}".broadcast_jobs (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_by   UUID NOT NULL REFERENCES "{schema}".users(id),
        title        VARCHAR(200) NOT NULL,
        body         TEXT NOT NULL,
        data         JSONB DEFAULT '{{}}'::jsonb,
        filters      JSONB DEFAULT '{{}}'::jsonb,
        channels     JSONB DEFAULT '["telegram","in_app"]'::jsonb,
        total        INTEGER DEFAULT 0,
        sent         INTEGER DEFAULT 0,
        failed       INTEGER DEFAULT 0,
        status       VARCHAR(15) DEFAULT 'queued',
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        started_at   TIMESTAMPTZ,
        completed_at TIMESTAMPTZ
    )
    """,
    # student_progress (011)
    """
    CREATE TABLE IF NOT EXISTS "{schema}".student_progress (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id UUID NOT NULL REFERENCES "{schema}".students(id) ON DELETE CASCADE,
        group_id   UUID NOT NULL REFERENCES "{schema}".groups(id),
        teacher_id UUID REFERENCES "{schema}".teachers(id),
        date       DATE NOT NULL,
        score      DECIMAL(5,2),
        note       TEXT,
        is_late    BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    # lesson_cancellations (011 + 012)
    """
    CREATE TABLE IF NOT EXISTS "{schema}".lesson_cancellations (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        group_id         UUID NOT NULL REFERENCES "{schema}".groups(id) ON DELETE CASCADE,
        scope            VARCHAR(20)  NOT NULL DEFAULT 'group',
        student_id       UUID         REFERENCES "{schema}".students(id) ON DELETE CASCADE,
        lesson_date      DATE         NOT NULL,
        reason           TEXT         NULL,
        status           VARCHAR(20)  NOT NULL DEFAULT 'pending',
        payment_adjusted BOOLEAN      NOT NULL DEFAULT FALSE,
        created_by       UUID         REFERENCES "{schema}".users(id) ON DELETE SET NULL,
        reviewed_by      UUID         NULL,
        reviewed_at      TIMESTAMPTZ  NULL,
        created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
    # payment_adjustments (011)
    """
    CREATE TABLE IF NOT EXISTS "{schema}".payment_adjustments (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id       UUID NOT NULL REFERENCES "{schema}".students(id) ON DELETE CASCADE,
        group_id         UUID         REFERENCES "{schema}".groups(id) ON DELETE SET NULL,
        cancellation_id  UUID         REFERENCES "{schema}".lesson_cancellations(id) ON DELETE SET NULL,
        adj_type         VARCHAR(20)  NOT NULL,
        amount           NUMERIC(12,2) NOT NULL DEFAULT 0,
        days_adjusted    NUMERIC(6,2)  NOT NULL DEFAULT 0,
        note             TEXT         NULL,
        created_by       UUID         REFERENCES "{schema}".users(id) ON DELETE SET NULL,
        created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
]


# Mavjud tenantlarga ALTER ADD COLUMN — yetishmayotgan ustunlarni qo'shadi (008-014)
_ALTER_STATEMENTS = [
    # 008
    'ALTER TABLE "{schema}".teachers ADD COLUMN IF NOT EXISTS is_approved BOOLEAN NOT NULL DEFAULT TRUE',
    'ALTER TABLE "{schema}".teachers ADD COLUMN IF NOT EXISTS created_by UUID',
    'ALTER TABLE "{schema}".teachers ADD COLUMN IF NOT EXISTS created_by_role VARCHAR(20)',
    # 010
    'ALTER TABLE "{schema}".students ADD COLUMN IF NOT EXISTS is_rejected BOOLEAN NOT NULL DEFAULT FALSE',
    "ALTER TABLE \"{schema}\".students ADD COLUMN IF NOT EXISTS pending_group_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
    # 011
    'ALTER TABLE "{schema}".attendance ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ NULL',
    'ALTER TABLE "{schema}".attendance ADD COLUMN IF NOT EXISTS is_late_entry BOOLEAN NOT NULL DEFAULT FALSE',
    'ALTER TABLE "{schema}".groups ADD COLUMN IF NOT EXISTS attendance_deadline_hours SMALLINT NOT NULL DEFAULT 2',
    'ALTER TABLE "{schema}".students ADD COLUMN IF NOT EXISTS referral_source VARCHAR(30) NULL',
    'ALTER TABLE "{schema}".students ADD COLUMN IF NOT EXISTS referred_by_teacher_id UUID NULL',
    'ALTER TABLE "{schema}".students ADD COLUMN IF NOT EXISTS leave_reason VARCHAR(50) NULL',
    'ALTER TABLE "{schema}".students ADD COLUMN IF NOT EXISTS churn_teacher_id UUID NULL',
    "ALTER TABLE \"{schema}\".students ADD COLUMN IF NOT EXISTS progress_dates JSONB NOT NULL DEFAULT '[]'::jsonb",
    # 012
    "ALTER TABLE \"{schema}\".lesson_cancellations ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending'",
    'ALTER TABLE "{schema}".lesson_cancellations ADD COLUMN IF NOT EXISTS reviewed_by UUID NULL',
    'ALTER TABLE "{schema}".lesson_cancellations ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NULL',
    # 012-fix — yetishmayotgan ustunlarni qo'shish (eski noto'g'ri provisioning DDL natijasida)
    "ALTER TABLE \"{schema}\".lesson_cancellations ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'group'",
    'ALTER TABLE "{schema}".lesson_cancellations ADD COLUMN IF NOT EXISTS student_id UUID NULL',
    'ALTER TABLE "{schema}".lesson_cancellations ADD COLUMN IF NOT EXISTS lesson_date DATE NULL',
    'ALTER TABLE "{schema}".lesson_cancellations ADD COLUMN IF NOT EXISTS payment_adjusted BOOLEAN NOT NULL DEFAULT FALSE',
    'ALTER TABLE "{schema}".lesson_cancellations ADD COLUMN IF NOT EXISTS created_by UUID NULL',
    # eski "date"/"teacher_id" ustunlari mavjud bo'lsa, ularni mosaktiv qilamiz (DO blok — ustun bo'lmasa ham ishlaydi)
    """DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = '{schema}' AND table_name = 'lesson_cancellations' AND column_name = 'date') THEN
            EXECUTE 'UPDATE "{schema}".lesson_cancellations SET lesson_date = date WHERE lesson_date IS NULL AND date IS NOT NULL';
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = '{schema}' AND table_name = 'lesson_cancellations' AND column_name = 'teacher_id') THEN
            EXECUTE 'ALTER TABLE "{schema}".lesson_cancellations ALTER COLUMN teacher_id DROP NOT NULL';
        END IF;
    END $$""",
    # payment_adjustments — yetishmayotgan ustunlar
    'ALTER TABLE "{schema}".payment_adjustments ADD COLUMN IF NOT EXISTS group_id UUID NULL',
    'ALTER TABLE "{schema}".payment_adjustments ADD COLUMN IF NOT EXISTS cancellation_id UUID NULL',
    "ALTER TABLE \"{schema}\".payment_adjustments ADD COLUMN IF NOT EXISTS adj_type VARCHAR(20) NOT NULL DEFAULT 'credit'",
    'ALTER TABLE "{schema}".payment_adjustments ADD COLUMN IF NOT EXISTS days_adjusted NUMERIC(6,2) NOT NULL DEFAULT 0',
    'ALTER TABLE "{schema}".payment_adjustments ALTER COLUMN amount SET DEFAULT 0',
    'ALTER TABLE "{schema}".payment_adjustments ALTER COLUMN amount DROP NOT NULL',
    # 013
    'ALTER TABLE "{schema}".groups ADD COLUMN IF NOT EXISTS progress_deadline_day SMALLINT NOT NULL DEFAULT 25',
    'ALTER TABLE "{schema}".groups ADD COLUMN IF NOT EXISTS progress_deadline_hour SMALLINT NOT NULL DEFAULT 23',
    'ALTER TABLE "{schema}".student_progress ADD COLUMN IF NOT EXISTS is_late BOOLEAN NOT NULL DEFAULT FALSE',
    # 014 — telegram link + notification system
    'ALTER TABLE "{schema}".users ADD COLUMN IF NOT EXISTS telegram_link_token VARCHAR(64) UNIQUE',
    'ALTER TABLE "{schema}".users ADD COLUMN IF NOT EXISTS telegram_link_expires_at TIMESTAMPTZ',
    'ALTER TABLE "{schema}".users ADD COLUMN IF NOT EXISTS telegram_linked_at TIMESTAMPTZ',
    "ALTER TABLE \"{schema}\".notifications ADD COLUMN IF NOT EXISTS category VARCHAR(30) NOT NULL DEFAULT 'system'",
    "ALTER TABLE \"{schema}\".notifications ADD COLUMN IF NOT EXISTS priority VARCHAR(15) NOT NULL DEFAULT 'normal'",
    "ALTER TABLE \"{schema}\".notifications ADD COLUMN IF NOT EXISTS status VARCHAR(15) NOT NULL DEFAULT 'queued'",
    'ALTER TABLE "{schema}".notifications ADD COLUMN IF NOT EXISTS error TEXT',
    'ALTER TABLE "{schema}".notifications ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0',
    'ALTER TABLE "{schema}".notifications ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(120)',
    'ALTER TABLE "{schema}".notifications ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ',
    # 015 — user_roles (multi-role)
    """
    CREATE TABLE IF NOT EXISTS "{schema}".user_roles (
        user_id    UUID NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE,
        role       VARCHAR(20) NOT NULL,
        branch_id  UUID NULL,
        is_active  BOOLEAN NOT NULL DEFAULT TRUE,
        granted_by UUID NULL,
        granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, role)
    )
    """,
    'CREATE INDEX IF NOT EXISTS idx_user_roles_role_{schema_safe} ON "{schema}".user_roles(role)',
    'CREATE INDEX IF NOT EXISTS idx_user_roles_user_active_{schema_safe} ON "{schema}".user_roles(user_id, is_active)',
    # Backfill: mavjud users.role ni user_roles ga ko'chirish
    """
    INSERT INTO "{schema}".user_roles (user_id, role, branch_id, is_active)
    SELECT id, role, branch_id, is_active FROM "{schema}".users
    WHERE role IS NOT NULL
    ON CONFLICT (user_id, role) DO NOTHING
    """,
]


# Public schema DDL (014)
_PUBLIC_DDL = [
    """
    CREATE TABLE IF NOT EXISTS public.telegram_link_tokens (
        token        VARCHAR(64) PRIMARY KEY,
        tenant_slug  VARCHAR(50) NOT NULL,
        user_id      UUID NOT NULL,
        expires_at   TIMESTAMPTZ NOT NULL,
        created_at   TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_link_tokens_expires ON public.telegram_link_tokens(expires_at)",
]


async def provision_tenant_schema(session: AsyncSession, schema: str) -> None:
    """Yangi tenant uchun schema + barcha jadvallar + indekslar."""
    await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    for sql_template in _TENANT_TABLES_SQL:
        await session.execute(text(sql_template.format(schema=schema)))
    # Notification system indekslari (014)
    schema_safe = schema.replace("-", "_")
    await session.execute(text(
        f'CREATE INDEX IF NOT EXISTS idx_notifications_user_unread_{schema_safe} '
        f'ON "{schema}".notifications(user_id, is_read, created_at DESC)'
    ))
    await session.execute(text(
        f'CREATE INDEX IF NOT EXISTS idx_notifications_status_sched_{schema_safe} '
        f'ON "{schema}".notifications(status, scheduled_at)'
    ))
    await session.execute(text(
        f'CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_dedupe_{schema_safe} '
        f'ON "{schema}".notifications(user_id, dedupe_key) '
        f'WHERE dedupe_key IS NOT NULL'
    ))
    # user_roles indekslari (015)
    await session.execute(text(
        f'CREATE INDEX IF NOT EXISTS idx_user_roles_role_{schema_safe} '
        f'ON "{schema}".user_roles(role)'
    ))
    await session.execute(text(
        f'CREATE INDEX IF NOT EXISTS idx_user_roles_user_active_{schema_safe} '
        f'ON "{schema}".user_roles(user_id, is_active)'
    ))
    # Public schema (telegram_link_tokens) — 014
    for sql in _PUBLIC_DDL:
        await session.execute(text(sql))


async def upgrade_tenant_schema(session: AsyncSession, schema: str) -> dict:
    """
    Mavjud tenant schema'ga 008-014 migration ustunlarini va public DDL'ni
    tatbiq etadi. Idempotent.
    """
    applied = []
    errors = []

    # 0. Public schema DDL
    for sql in _PUBLIC_DDL:
        try:
            await session.execute(text(sql))
            applied.append(sql.strip().split("\n")[0][:60])
        except Exception as e:
            errors.append(f"PUBLIC: {str(e)[:120]}")

    # 1. Tenant tables
    for sql_template in _TENANT_TABLES_SQL:
        try:
            await session.execute(text(sql_template.format(schema=schema)))
        except Exception as e:
            errors.append(f"CREATE: {str(e)[:120]}")

    # 2. ALTER statements — har bir statement o'z savepoint ida (bittasi xato bersa qolganlari ishlaydi)
    schema_safe = schema.replace("-", "_")
    for stmt in _ALTER_STATEMENTS:
        sql = stmt.format(schema=schema, schema_safe=schema_safe)
        try:
            async with session.begin_nested():
                await session.execute(text(sql))
            if "ADD COLUMN" in sql:
                applied.append(sql.split("ADD COLUMN IF NOT EXISTS")[1].split()[0])
            else:
                applied.append(sql[:60])
        except Exception as e:
            errors.append(f"{sql[:80]}... -> {str(e)[:120]}")

    return {"applied": applied, "errors": errors}


async def create_default_branch(
    session: AsyncSession,
    schema: str,
    name: str = "Asosiy filial",
    phone: Optional[str] = None,
    address: Optional[str] = None,
) -> str:
    result = await session.execute(
        text(
            f'INSERT INTO "{schema}".branches (name, address, phone, is_main, is_active) '
            f"VALUES (:name, :address, :phone, TRUE, TRUE) RETURNING id"
        ),
        {"name": name, "address": address, "phone": phone},
    )
    return str(result.scalar_one())


async def create_admin_user(
    session: AsyncSession,
    schema: str,
    email: str,
    password: str,
    first_name: str,
    last_name: Optional[str] = None,
    phone: Optional[str] = None,
    branch_id: Optional[str] = None,
    role: str = "admin",
) -> str:
    pw_hash = hash_password(password)
    result = await session.execute(
        text(
            f'INSERT INTO "{schema}".users '
            f"(first_name, last_name, email, password_hash, role, phone, "
            f"branch_id, is_active, is_verified) "
            f"VALUES (:fn, :ln, :email, :pw, :role, :phone, "
            f":branch_id, TRUE, TRUE) RETURNING id"
        ),
        {
            "fn": first_name, "ln": last_name, "email": email, "pw": pw_hash,
            "role": role, "phone": phone, "branch_id": branch_id,
        },
    )
    return str(result.scalar_one())
