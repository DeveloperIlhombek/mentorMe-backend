"""
KPI va Marketing modullari uchun jadvallar yaratish.
Ishlatish: python create_kpi_marketing_tables.py
"""
import asyncio
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://edusaas:edusaas_pass@localhost:5432/edusaas"
).replace("postgresql+asyncpg://", "postgresql://")


async def main():
    conn = await asyncpg.connect(DB_URL)
    tenants = await conn.fetch(
        "SELECT schema_name, slug FROM public.tenants WHERE is_active = true"
    )
    print(f"📋 {len(tenants)} ta tenant")

    for t in tenants:
        s = t["schema_name"]
        print(f"\n🔧 {s}")

        # ── KPI ──────────────────────────────────────────────────────────

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".kpi_metrics (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug         VARCHAR(80) NOT NULL,
                name         VARCHAR(200) NOT NULL,
                description  TEXT,
                metric_type  VARCHAR(30) NOT NULL DEFAULT 'percentage'
                                 CHECK (metric_type IN
                                   ('percentage','count','rating','sum','custom')),
                direction    VARCHAR(20) NOT NULL DEFAULT 'higher_better'
                                 CHECK (direction IN ('higher_better','lower_better')),
                unit         VARCHAR(20) DEFAULT '%',
                is_active    BOOLEAN NOT NULL DEFAULT TRUE,
                created_by   UUID REFERENCES "{s}".users(id) ON DELETE SET NULL,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(slug)
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".kpi_rules (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                metric_id      UUID NOT NULL
                                   REFERENCES "{s}".kpi_metrics(id) ON DELETE CASCADE,
                threshold_min  DECIMAL(10,2),
                threshold_max  DECIMAL(10,2),
                reward_type    VARCHAR(30) NOT NULL
                                   CHECK (reward_type IN
                                     ('bonus_pct','bonus_sum',
                                      'penalty_pct','penalty_sum','none')),
                reward_value   DECIMAL(12,2) NOT NULL DEFAULT 0,
                period         VARCHAR(20) NOT NULL DEFAULT 'monthly'
                                   CHECK (period IN ('monthly','weekly')),
                label          VARCHAR(100),
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".kpi_results (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                teacher_id     UUID NOT NULL
                                   REFERENCES "{s}".teachers(id) ON DELETE CASCADE,
                metric_id      UUID NOT NULL
                                   REFERENCES "{s}".kpi_metrics(id) ON DELETE CASCADE,
                period_month   SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
                period_year    SMALLINT NOT NULL,
                actual_value   DECIMAL(10,2),
                rule_id        UUID REFERENCES "{s}".kpi_rules(id) ON DELETE SET NULL,
                reward_amount  DECIMAL(12,2) NOT NULL DEFAULT 0,
                notes          TEXT,
                calculated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                status         VARCHAR(20) NOT NULL DEFAULT 'pending'
                                   CHECK (status IN ('pending','approved','paid')),
                UNIQUE(teacher_id, metric_id, period_month, period_year)
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".kpi_payslips (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                teacher_id     UUID NOT NULL
                                   REFERENCES "{s}".teachers(id) ON DELETE CASCADE,
                period_month   SMALLINT NOT NULL,
                period_year    SMALLINT NOT NULL,
                base_salary    DECIMAL(15,2) NOT NULL DEFAULT 0,
                total_bonus    DECIMAL(15,2) NOT NULL DEFAULT 0,
                total_penalty  DECIMAL(15,2) NOT NULL DEFAULT 0,
                net_salary     DECIMAL(15,2) NOT NULL DEFAULT 0,
                status         VARCHAR(20) NOT NULL DEFAULT 'draft'
                                   CHECK (status IN ('draft','approved','paid')),
                approved_by    UUID REFERENCES "{s}".users(id) ON DELETE SET NULL,
                approved_at    TIMESTAMPTZ,
                pdf_url        TEXT,
                notes          TEXT,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(teacher_id, period_month, period_year)
            )
        """)
        print("  ✅ KPI jadvallari")

        # ── Marketing ────────────────────────────────────────────────────

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".campaigns (
                id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name                    VARCHAR(200) NOT NULL,
                description             TEXT,
                type                    VARCHAR(30) NOT NULL DEFAULT 'referral'
                                            CHECK (type IN
                                              ('referral','invitation','seasonal','loyalty')),
                referrer_reward_type    VARCHAR(30) DEFAULT 'bonus_sum'
                                            CHECK (referrer_reward_type IN
                                              ('bonus_sum','discount_pct','none')),
                referrer_reward_value   DECIMAL(12,2) DEFAULT 0,
                new_student_discount_type VARCHAR(20) DEFAULT 'percent'
                                            CHECK (new_student_discount_type IN
                                              ('percent','fixed','none')),
                new_student_discount_value DECIMAL(12,2) DEFAULT 0,
                max_uses                INTEGER,
                used_count              INTEGER NOT NULL DEFAULT 0,
                starts_at               TIMESTAMPTZ,
                ends_at                 TIMESTAMPTZ,
                is_active               BOOLEAN NOT NULL DEFAULT TRUE,
                created_by              UUID REFERENCES "{s}".users(id) ON DELETE SET NULL,
                created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".referral_codes (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id    UUID UNIQUE NOT NULL
                                  REFERENCES "{s}".students(id) ON DELETE CASCADE,
                campaign_id   UUID REFERENCES "{s}".campaigns(id) ON DELETE SET NULL,
                code          VARCHAR(16) UNIQUE NOT NULL,
                total_uses    INTEGER NOT NULL DEFAULT 0,
                total_earned  DECIMAL(12,2) NOT NULL DEFAULT 0,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".referral_uses (
                id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code_id                UUID NOT NULL
                                           REFERENCES "{s}".referral_codes(id)
                                           ON DELETE CASCADE,
                new_student_id         UUID NOT NULL
                                           REFERENCES "{s}".students(id)
                                           ON DELETE CASCADE,
                referrer_bonus         DECIMAL(12,2) NOT NULL DEFAULT 0,
                new_student_discount   DECIMAL(12,2) NOT NULL DEFAULT 0,
                status                 VARCHAR(20) NOT NULL DEFAULT 'pending'
                                           CHECK (status IN ('pending','paid','cancelled')),
                paid_at                TIMESTAMPTZ,
                created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(code_id, new_student_id)
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".invitations (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id      UUID NOT NULL
                                    REFERENCES "{s}".students(id) ON DELETE CASCADE,
                campaign_id     UUID REFERENCES "{s}".campaigns(id) ON DELETE SET NULL,
                code            VARCHAR(32) UNIQUE NOT NULL,
                discount_type   VARCHAR(20) NOT NULL DEFAULT 'percent'
                                    CHECK (discount_type IN ('percent','fixed','none')),
                discount_value  DECIMAL(12,2) NOT NULL DEFAULT 0,
                pdf_url         TEXT,
                qr_data         TEXT,
                used_by         UUID REFERENCES "{s}".students(id) ON DELETE SET NULL,
                used_at         TIMESTAMPTZ,
                expires_at      TIMESTAMPTZ,
                is_active       BOOLEAN NOT NULL DEFAULT TRUE,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute(f"""
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
                                     DEFAULT UPPER(SUBSTRING(gen_random_uuid()::TEXT,1,12)),
                is_public        BOOLEAN NOT NULL DEFAULT TRUE,
                metadata         JSONB DEFAULT '{{}}'
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".churn_risks (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id    UUID NOT NULL
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
                calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(student_id)
            )
        """)
        print("  ✅ Marketing jadvallari")

        # ── Indekslar ────────────────────────────────────────────────────
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_kpi_results_teacher_{s[-8:]}
            ON "{s}".kpi_results(teacher_id, period_year, period_month)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_kpi_payslips_teacher_{s[-8:]}
            ON "{s}".kpi_payslips(teacher_id, period_year, period_month)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_ref_code_{s[-8:]}
            ON "{s}".referral_codes(code)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_churn_risk_{s[-8:]}
            ON "{s}".churn_risks(risk_level, risk_score DESC)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_invitations_code_{s[-8:]}
            ON "{s}".invitations(code)
        """)
        print("  ✅ Indekslar")

        # ── Default KPI metrikalari ───────────────────────────────────────
        await conn.execute(f"""
            INSERT INTO "{s}".kpi_metrics
                (slug, name, metric_type, direction, unit, description)
            VALUES
                ('attendance_punctuality',   'Davomat o''z vaqtidaligi',
                 'percentage', 'higher_better', '%',
                 'Darsdan 15 daqiqa ichida davomat kiritilgan kunlar foizi'),
                ('student_attendance_rate',  'Guruh davomati o''rtachasi',
                 'percentage', 'higher_better', '%',
                 'O''qituvchi guruhlarida o''quvchi davomati o''rtachasi'),
                ('lesson_materials',         'Dars materiallari yuklash',
                 'count',      'higher_better', 'ta',
                 'Oyda yuklangan dars va mashqlar soni'),
                ('student_rating',           'O''quvchi baholash reytingi',
                 'rating',     'higher_better', 'yulduz',
                 'O''quvchilar tomonidan oylik so''rovnoma baholash'),
                ('test_avg_score',           'Test o''rtacha balli',
                 'percentage', 'higher_better', '%',
                 'O''quvchilar test natijalari o''rtachasi')
            ON CONFLICT (slug) DO NOTHING
        """)
        print("  ✅ Default KPI metrikalari")

        # teachers jadvaliga kpi_calc_day qo'shish
        await conn.execute(f"""
            ALTER TABLE "{s}".teachers
            ADD COLUMN IF NOT EXISTS kpi_calc_day SMALLINT
                CHECK (kpi_calc_day BETWEEN 1 AND 31)
        """)
        print("  ✅ teachers: kpi_calc_day qo'shildi")

    await conn.close()
    print("\n🎉 Barcha jadvallar yaratildi!")
    print("Keyin: alembic stamp 005_kpi_marketing")


if __name__ == "__main__":
    asyncio.run(main())
