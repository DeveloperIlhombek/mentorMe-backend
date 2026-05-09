"""014_notification_system_v2

Notification tizimini kengaytirish:
  - notifications: priority, category, status, error, attempts, dedupe_key, scheduled_at
  - notification_preferences: yangi jadval
  - broadcast_jobs: yangi jadval
  - users: telegram_link_token, telegram_link_expires_at, telegram_linked_at
  - public.telegram_link_tokens: deep-link mapping

Multi-tenant: barcha tenant schema lar bo'ylab yuriladi.
"""
from alembic import op
import sqlalchemy as sa

revision = '014_notification_system_v2'
down_revision = '013'
branch_labels = None
depends_on = None


def get_tenant_schemas(conn):
    result = conn.execute(sa.text(
        "SELECT schema_name FROM public.tenants WHERE is_active = true"
    ))
    return [row[0] for row in result]


def upgrade():
    conn = op.get_bind()

    # ── public.telegram_link_tokens ──────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS public.telegram_link_tokens (
            token        VARCHAR(64) PRIMARY KEY,
            tenant_slug  VARCHAR(50) NOT NULL,
            user_id      UUID NOT NULL,
            expires_at   TIMESTAMPTZ NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_link_tokens_expires
        ON public.telegram_link_tokens(expires_at)
    """))

    schemas = get_tenant_schemas(conn)

    for schema in schemas:
        # Schema'da notifications jadvali bormi? (Bootstrap migrations
        # qo'llanmagan tenantlarni xavfsiz skip qilamiz.)
        has_notif = conn.execute(sa.text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = :s AND table_name = 'notifications'
        """), {"s": schema}).first()
        if not has_notif:
            print(f"⚠️  {schema}: notifications jadvali yo'q — skip (bootstrap migrations kerak)")
            continue

        conn.execute(sa.text(f'SET search_path TO "{schema}", public'))

        # ── notifications kengaytmasi ──────────────────────────────────
        for col, ddl in [
            ("category",     "VARCHAR(30) NOT NULL DEFAULT 'system'"),
            ("priority",     "VARCHAR(15) NOT NULL DEFAULT 'normal'"),
            ("status",       "VARCHAR(15) NOT NULL DEFAULT 'queued'"),
            ("error",        "TEXT"),
            ("attempts",     "INTEGER DEFAULT 0"),
            ("dedupe_key",   "VARCHAR(120)"),
            ("scheduled_at", "TIMESTAMPTZ"),
        ]:
            conn.execute(sa.text(f"""
                ALTER TABLE "{schema}".notifications
                ADD COLUMN IF NOT EXISTS {col} {ddl}
            """))

        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_notifications_user_unread_{schema}
            ON "{schema}".notifications(user_id, is_read, created_at DESC)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_notifications_status_sched_{schema}
            ON "{schema}".notifications(status, scheduled_at)
        """))
        # Dedupe — partial UNIQUE (NULL dedupe_key bo'lganda cheklov yo'q)
        conn.execute(sa.text(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_user_dedupe_{schema}
            ON "{schema}".notifications(user_id, dedupe_key)
            WHERE dedupe_key IS NOT NULL
        """))

        # ── notification_preferences ───────────────────────────────────
        conn.execute(sa.text(f"""
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
        """))

        # ── broadcast_jobs ─────────────────────────────────────────────
        conn.execute(sa.text(f"""
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
        """))

        # ── users.telegram linking maydonlari ──────────────────────────
        for col, ddl in [
            ("telegram_link_token",      "VARCHAR(64) UNIQUE"),
            ("telegram_link_expires_at", "TIMESTAMPTZ"),
            ("telegram_linked_at",       "TIMESTAMPTZ"),
        ]:
            conn.execute(sa.text(f"""
                ALTER TABLE "{schema}".users
                ADD COLUMN IF NOT EXISTS {col} {ddl}
            """))

        print(f"✅ {schema}: notification system v2 yangilanishi qo'llandi")

    conn.execute(sa.text("SET search_path TO public"))


def downgrade():
    conn = op.get_bind()
    schemas = get_tenant_schemas(conn)

    for schema in schemas:
        conn.execute(sa.text(f'SET search_path TO "{schema}", public'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".broadcast_jobs CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".notification_preferences CASCADE'))
        for col in ("category", "priority", "status", "error", "attempts", "dedupe_key", "scheduled_at"):
            conn.execute(sa.text(f'ALTER TABLE "{schema}".notifications DROP COLUMN IF EXISTS {col}'))
        for col in ("telegram_link_token", "telegram_link_expires_at", "telegram_linked_at"):
            conn.execute(sa.text(f'ALTER TABLE "{schema}".users DROP COLUMN IF EXISTS {col}'))

    conn.execute(sa.text("SET search_path TO public"))
    conn.execute(sa.text("DROP TABLE IF EXISTS public.telegram_link_tokens CASCADE"))
