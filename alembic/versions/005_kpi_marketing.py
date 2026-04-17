"""
005_kpi_marketing

KPI va Marketing modullari uchun jadvallar.

Revision ID: 005_kpi_marketing
Revises: 004_student_extended
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_kpi_marketing"
down_revision: Union[str, None] = "004_student_extended"
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

    for s in schemas:

        # ── Teachers: kpi_calc_day ────────────────────────────────────
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".teachers
            ADD COLUMN IF NOT EXISTS kpi_calc_day SMALLINT
                CHECK (kpi_calc_day BETWEEN 1 AND 31)
        """))

        # ── KPI: metrics ─────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".kpi_metrics (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug         VARCHAR(80)  NOT NULL UNIQUE,
                name         VARCHAR(200) NOT NULL,
                description  TEXT,
                metric_type  VARCHAR(30)  NOT NULL DEFAULT 'percentage'
                                 CHECK (metric_type IN
                                   ('percentage','count','rating','sum','custom')),
                direction    VARCHAR(20)  NOT NULL DEFAULT 'higher_better'
                                 CHECK (direction IN ('higher_better','lower_better')),
                unit         VARCHAR(20)  DEFAULT '%',
                is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
                created_by   UUID REFERENCES "{s}".users(id) ON DELETE SET NULL,
                created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """))

        # ── KPI: rules ────────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".kpi_rules (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                metric_id     UUID NOT NULL
                                  REFERENCES "{s}".kpi_metrics(id) ON DELETE CASCADE,
                threshold_min DECIMAL(10,2),
                threshold_max DECIMAL(10,2),
                reward_type   VARCHAR(30) NOT NULL DEFAULT 'none'
                                  CHECK (reward_type IN
                                    ('bonus_pct','bonus_sum',
                                     'penalty_pct','penalty_sum','none')),
                reward_value  DECIMAL(12,2) NOT NULL DEFAULT 0,
                period        VARCHAR(20) NOT NULL DEFAULT 'monthly'
                                  CHECK (period IN ('monthly','weekly')),
                label         VARCHAR(100),
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # ── KPI: results ──────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".kpi_results (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                teacher_id    UUID NOT NULL
                                  REFERENCES "{s}".teachers(id) ON DELETE CASCADE,
                metric_id     UUID NOT NULL
                                  REFERENCES "{s}".kpi_metrics(id) ON DELETE CASCADE,
                period_month  SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
                period_year   SMALLINT NOT NULL,
                actual_value  DECIMAL(10,2),
                rule_id       UUID REFERENCES "{s}".kpi_rules(id) ON DELETE SET NULL,
                reward_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                notes         TEXT,
                calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                status        VARCHAR(20) NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','approved','paid')),
                UNIQUE (teacher_id, metric_id, period_month, period_year)
            )
        """))

        # ── KPI: payslips ─────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".kpi_payslips (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                teacher_id    UUID NOT NULL
                                  REFERENCES "{s}".teachers(id) ON DELETE CASCADE,
                period_month  SMALLINT NOT NULL,
                period_year   SMALLINT NOT NULL,
                base_salary   DECIMAL(15,2) NOT NULL DEFAULT 0,
                total_bonus   DECIMAL(15,2) NOT NULL DEFAULT 0,
                total_penalty DECIMAL(15,2) NOT NULL DEFAULT 0,
                net_salary    DECIMAL(15,2) NOT NULL DEFAULT 0,
                status        VARCHAR(20) NOT NULL DEFAULT 'draft'
                                  CHECK (status IN ('draft','approved','paid')),
                approved_by   UUID REFERENCES "{s}".users(id) ON DELETE SET NULL,
                approved_at   TIMESTAMPTZ,
                pdf_url       TEXT,
                notes         TEXT,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (teacher_id, period_month, period_year)
            )
        """))

        # ── Marketing: campaigns ──────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".campaigns (
                id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name                       VARCHAR(200) NOT NULL,
                description                TEXT,
                type                       VARCHAR(30) NOT NULL DEFAULT 'referral'
                                               CHECK (type IN
                                                 ('referral','invitation',
                                                  'seasonal','loyalty')),
                referrer_reward_type       VARCHAR(30) DEFAULT 'bonus_sum'
                                               CHECK (referrer_reward_type IN
                                                 ('bonus_sum','discount_pct','none')),
                referrer_reward_value      DECIMAL(12,2) DEFAULT 0,
                new_student_discount_type  VARCHAR(20) DEFAULT 'percent'
                                               CHECK (new_student_discount_type IN
                                                 ('percent','fixed','none')),
                new_student_discount_value DECIMAL(12,2) DEFAULT 0,
                max_uses                   INTEGER,
                used_count                 INTEGER NOT NULL DEFAULT 0,
                starts_at                  TIMESTAMPTZ,
                ends_at                    TIMESTAMPTZ,
                is_active                  BOOLEAN NOT NULL DEFAULT TRUE,
                created_by                 UUID REFERENCES "{s}".users(id)
                                               ON DELETE SET NULL,
                created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # ── Marketing: referral_codes ─────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".referral_codes (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id   UUID UNIQUE NOT NULL
                                 REFERENCES "{s}".students(id) ON DELETE CASCADE,
                campaign_id  UUID REFERENCES "{s}".campaigns(id) ON DELETE SET NULL,
                code         VARCHAR(16) UNIQUE NOT NULL,
                total_uses   INTEGER NOT NULL DEFAULT 0,
                total_earned DECIMAL(12,2) NOT NULL DEFAULT 0,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # ── Marketing: referral_uses ──────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".referral_uses (
                id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code_id              UUID NOT NULL
                                         REFERENCES "{s}".referral_codes(id)
                                         ON DELETE CASCADE,
                new_student_id       UUID NOT NULL
                                         REFERENCES "{s}".students(id)
                                         ON DELETE CASCADE,
                referrer_bonus       DECIMAL(12,2) NOT NULL DEFAULT 0,
                new_student_discount DECIMAL(12,2) NOT NULL DEFAULT 0,
                status               VARCHAR(20) NOT NULL DEFAULT 'pending'
                                         CHECK (status IN
                                           ('pending','paid','cancelled')),
                paid_at              TIMESTAMPTZ,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (code_id, new_student_id)
            )
        """))

        # ── Marketing: invitations ────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".invitations (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id     UUID NOT NULL
                                   REFERENCES "{s}".students(id) ON DELETE CASCADE,
                campaign_id    UUID REFERENCES "{s}".campaigns(id) ON DELETE SET NULL,
                code           VARCHAR(32) UNIQUE NOT NULL,
                discount_type  VARCHAR(20) NOT NULL DEFAULT 'percent'
                                   CHECK (discount_type IN
                                     ('percent','fixed','none')),
                discount_value DECIMAL(12,2) NOT NULL DEFAULT 0,
                pdf_url        TEXT,
                qr_data        TEXT,
                used_by        UUID REFERENCES "{s}".students(id) ON DELETE SET NULL,
                used_at        TIMESTAMPTZ,
                expires_at     TIMESTAMPTZ,
                is_active      BOOLEAN NOT NULL DEFAULT TRUE,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # ── Marketing: certificates ───────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".certificates (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id       UUID NOT NULL
                                     REFERENCES "{s}".students(id) ON DELETE CASCADE,
                certificate_type VARCHAR(30) NOT NULL DEFAULT 'course'
                                     CHECK (certificate_type IN
                                       ('course','level','attendance','custom')),
                title            VARCHAR(300) NOT NULL,
                description      TEXT,
                issued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                issued_by        UUID REFERENCES "{s}".users(id) ON DELETE SET NULL,
                pdf_url          TEXT,
                verify_code      VARCHAR(32) UNIQUE NOT NULL
                                     DEFAULT UPPER(SUBSTR(gen_random_uuid()::TEXT, 1, 12)),
                is_public        BOOLEAN NOT NULL DEFAULT TRUE,
                metadata         JSONB NOT NULL DEFAULT '{{}}'
            )
        """))

        # ── Marketing: churn_risks ────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".churn_risks (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id    UUID UNIQUE NOT NULL
                                  REFERENCES "{s}".students(id) ON DELETE CASCADE,
                risk_score    DECIMAL(5,2) NOT NULL DEFAULT 0
                                  CHECK (risk_score BETWEEN 0 AND 100),
                risk_level    VARCHAR(20) NOT NULL DEFAULT 'low'
                                  CHECK (risk_level IN
                                    ('low','medium','high','critical')),
                signals       JSONB NOT NULL DEFAULT '[]',
                action_taken  VARCHAR(200),
                resolved_at   TIMESTAMPTZ,
                notified_at   TIMESTAMPTZ,
                calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # ── Indekslar ─────────────────────────────────────────────────
        tag = s[-8:].replace("-", "_")

        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_kpi_results_t_{tag}
            ON "{s}".kpi_results (teacher_id, period_year, period_month)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_kpi_payslips_t_{tag}
            ON "{s}".kpi_payslips (teacher_id, period_year, period_month)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_ref_code_{tag}
            ON "{s}".referral_codes (code)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_churn_{tag}
            ON "{s}".churn_risks (risk_level, risk_score DESC)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_inv_code_{tag}
            ON "{s}".invitations (code)
        """))

        # ── Default KPI metrikalari ───────────────────────────────────
        conn.execute(sa.text(f"""
            INSERT INTO "{s}".kpi_metrics
                (slug, name, metric_type, direction, unit, description)
            VALUES
                ('attendance_punctuality',
                 'Davomat o''z vaqtidaligi',
                 'percentage', 'higher_better', '%',
                 'Darsdan 24 soat ichida davomat kiritilgan kunlar foizi'),

                ('student_attendance_rate',
                 'Guruh davomati o''rtachasi',
                 'percentage', 'higher_better', '%',
                 'O''qituvchi guruhlarida o''quvchi davomati o''rtachasi'),

                ('lesson_materials',
                 'Dars materiallari yuklash',
                 'count', 'higher_better', 'ta',
                 'Oyda yuklangan dars va mashqlar soni'),

                ('student_rating',
                 'O''quvchi baholash reytingi',
                 'rating', 'higher_better', 'yulduz',
                 'O''quvchilar tomonidan oylik so''rovnoma baholash'),

                ('test_avg_score',
                 'Test o''rtacha balli',
                 'percentage', 'higher_better', '%',
                 'O''quvchilar test natijalari o''rtachasi')

            ON CONFLICT (slug) DO NOTHING
        """))


def downgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)

    for s in schemas:
        # Marketing
        for tbl in ("churn_risks", "certificates", "invitations",
                    "referral_uses", "referral_codes", "campaigns"):
            conn.execute(sa.text(f'DROP TABLE IF EXISTS "{s}".{tbl} CASCADE'))

        # KPI
        for tbl in ("kpi_payslips", "kpi_results", "kpi_rules", "kpi_metrics"):
            conn.execute(sa.text(f'DROP TABLE IF EXISTS "{s}".{tbl} CASCADE'))

        # teachers column
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".teachers
            DROP COLUMN IF EXISTS kpi_calc_day
        """))