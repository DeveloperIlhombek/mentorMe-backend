"""
011_attendance_kpi_progress

Revision ID: 011_att_kpi_progress
Revises: 010_reject_pending_groups
Create Date: 2026-04-25

O'zgarishlar (har bir tenant schema uchun):
  1. branches.attendance_deadline_hours  — kechikish chegarasi (soat)
  2. attendance.submitted_at             — o'qituvchi qachon kiritgani
  3. attendance.is_late_entry            — kech kiritilganmi
  4. students.referral_source            — sarafan manbai
  5. students.referred_by_teacher_id     — kimning tavsiyasi bilan kelgan
  6. students.leave_reason               — ketish sababi
  7. students.churn_teacher_id           — ketishga sabab o'qituvchi
  8. students.progress_dates             — o'zlashtirish belgilash kunlari
  9. student_progress (yangi jadval)
  10. lesson_cancellations (yangi jadval)
  11. payment_adjustments (yangi jadval)
"""

revision = "011_att_kpi_progress"
down_revision = "010_reject_pending_groups"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def _schemas(conn) -> list:
    rows = conn.execute(
        sa.text("SELECT schema_name FROM public.tenants WHERE is_active = true")
    )
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)

    for s in schemas:
        # ── 1. branches — davomat kechikish chegarasi ─────────────────
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".branches '
            f'ADD COLUMN IF NOT EXISTS attendance_deadline_hours SMALLINT NOT NULL DEFAULT 2'
        ))

        # ── 2-3. attendance — kiritish vaqti + kechikish belgisi ───────
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".attendance '
            f'ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ NULL'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".attendance '
            f'ADD COLUMN IF NOT EXISTS is_late_entry BOOLEAN NOT NULL DEFAULT FALSE'
        ))

        # ── 4-8. students — sarafan, churn, progress kunlari ──────────
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".students '
            f"ADD COLUMN IF NOT EXISTS referral_source VARCHAR(30) NULL"
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".students '
            f'ADD COLUMN IF NOT EXISTS referred_by_teacher_id UUID NULL '
            f'REFERENCES "{s}".teachers(id) ON DELETE SET NULL'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".students '
            f"ADD COLUMN IF NOT EXISTS leave_reason VARCHAR(50) NULL"
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".students '
            f'ADD COLUMN IF NOT EXISTS churn_teacher_id UUID NULL '
            f'REFERENCES "{s}".teachers(id) ON DELETE SET NULL'
        ))
        conn.execute(sa.text(
            f'ALTER TABLE "{s}".students '
            f"ADD COLUMN IF NOT EXISTS progress_dates JSONB NOT NULL DEFAULT '[]'::jsonb"
        ))

        # ── 9. student_progress ───────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".student_progress (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id      UUID NOT NULL REFERENCES "{s}".students(id)  ON DELETE CASCADE,
                group_id        UUID          REFERENCES "{s}".groups(id)    ON DELETE SET NULL,
                teacher_id      UUID          REFERENCES "{s}".teachers(id)  ON DELETE SET NULL,
                period_month    SMALLINT NOT NULL,
                period_year     SMALLINT NOT NULL,
                scheduled_date  DATE     NOT NULL,
                score           NUMERIC(5, 2) NULL,
                status          VARCHAR(20)   NOT NULL DEFAULT 'pending',
                notes           TEXT          NULL,
                notified        BOOLEAN       NOT NULL DEFAULT FALSE,
                notified_at     TIMESTAMPTZ   NULL,
                submitted_at    TIMESTAMPTZ   NULL,
                created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_student_progress_date UNIQUE (student_id, scheduled_date)
            )
        """))
        conn.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS idx_sp_student_{s.replace("-","_")} '
            f'ON "{s}".student_progress (student_id)'
        ))
        conn.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS idx_sp_period_{s.replace("-","_")} '
            f'ON "{s}".student_progress (period_year, period_month)'
        ))
        conn.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS idx_sp_teacher_{s.replace("-","_")} '
            f'ON "{s}".student_progress (teacher_id)'
        ))

        # ── 10. lesson_cancellations ──────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".lesson_cancellations (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                group_id         UUID NOT NULL REFERENCES "{s}".groups(id)    ON DELETE CASCADE,
                scope            VARCHAR(20)  NOT NULL DEFAULT 'group',
                student_id       UUID          REFERENCES "{s}".students(id)  ON DELETE CASCADE,
                lesson_date      DATE         NOT NULL,
                reason           TEXT         NULL,
                payment_adjusted BOOLEAN      NOT NULL DEFAULT FALSE,
                created_by       UUID          REFERENCES "{s}".users(id)     ON DELETE SET NULL,
                created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS idx_lc_group_{s.replace("-","_")} '
            f'ON "{s}".lesson_cancellations (group_id)'
        ))
        conn.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS idx_lc_date_{s.replace("-","_")} '
            f'ON "{s}".lesson_cancellations (lesson_date)'
        ))

        # ── 11. payment_adjustments ───────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".payment_adjustments (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id       UUID NOT NULL REFERENCES "{s}".students(id)             ON DELETE CASCADE,
                group_id         UUID          REFERENCES "{s}".groups(id)               ON DELETE SET NULL,
                cancellation_id  UUID          REFERENCES "{s}".lesson_cancellations(id) ON DELETE SET NULL,
                adj_type         VARCHAR(20)  NOT NULL,
                amount           NUMERIC(12, 2) NOT NULL DEFAULT 0,
                days_adjusted    NUMERIC(6, 2)  NOT NULL DEFAULT 0,
                note             TEXT          NULL,
                created_by       UUID          REFERENCES "{s}".users(id) ON DELETE SET NULL,
                created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS idx_pa_student_{s.replace("-","_")} '
            f'ON "{s}".payment_adjustments (student_id)'
        ))
        conn.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS idx_pa_group_{s.replace("-","_")} '
            f'ON "{s}".payment_adjustments (group_id)'
        ))

        print(f"  ✅ {s}: barcha 011 o'zgarishlar qo'shildi")


def downgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)

    for s in schemas:
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{s}".payment_adjustments CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{s}".lesson_cancellations CASCADE'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{s}".student_progress CASCADE'))

        conn.execute(sa.text(f'ALTER TABLE "{s}".students DROP COLUMN IF EXISTS progress_dates'))
        conn.execute(sa.text(f'ALTER TABLE "{s}".students DROP COLUMN IF EXISTS churn_teacher_id'))
        conn.execute(sa.text(f'ALTER TABLE "{s}".students DROP COLUMN IF EXISTS leave_reason'))
        conn.execute(sa.text(f'ALTER TABLE "{s}".students DROP COLUMN IF EXISTS referred_by_teacher_id'))
        conn.execute(sa.text(f'ALTER TABLE "{s}".students DROP COLUMN IF EXISTS referral_source'))

        conn.execute(sa.text(f'ALTER TABLE "{s}".attendance DROP COLUMN IF EXISTS is_late_entry'))
        conn.execute(sa.text(f'ALTER TABLE "{s}".attendance DROP COLUMN IF EXISTS submitted_at'))
        conn.execute(sa.text(f'ALTER TABLE "{s}".branches   DROP COLUMN IF EXISTS attendance_deadline_hours'))

        print(f"  ↩️  {s}: 011 o'zgarishlar bekor qilindi")
