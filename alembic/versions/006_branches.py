"""
006_branches — Filial moduli migratsiyasi.
alembic/versions/006_branches.py

Revision ID: 006_branches
Revises: 005_kpi_marketing
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_branches"
down_revision: Union[str, None] = "005_kpi_marketing"
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

        # ── users: inspector roli va branch_id ───────────────────────
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".users
            ADD COLUMN IF NOT EXISTS branch_id UUID
                REFERENCES "{s}".branches(id) ON DELETE SET NULL
        """))

        # Role check constraint yangilash (inspector qo'shish)
        # Avval eski constraint ni olib tashlaymiz (agar mavjud bo'lsa)
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".users
            DROP CONSTRAINT IF EXISTS ck_user_role
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".users
            ADD CONSTRAINT ck_user_role
            CHECK (role IN ('super_admin','admin','teacher','student','parent','inspector'))
        """))

        # ── branches: manager_id ─────────────────────────────────────
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".branches
            ADD COLUMN IF NOT EXISTS manager_id UUID
                REFERENCES "{s}".users(id) ON DELETE SET NULL
        """))

        # ── branch_expenses ──────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".branch_expenses (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                branch_id        UUID NOT NULL
                                     REFERENCES "{s}".branches(id) ON DELETE CASCADE,
                requested_by     UUID
                                     REFERENCES "{s}".users(id) ON DELETE SET NULL,
                approved_by      UUID
                                     REFERENCES "{s}".users(id) ON DELETE SET NULL,
                title            VARCHAR(300) NOT NULL,
                description      TEXT,
                amount           DECIMAL(15,2) NOT NULL,
                category         VARCHAR(100),
                status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                                     CHECK (status IN
                                       ('pending','approved','rejected','paid')),
                rejected_reason  TEXT,
                approved_at      TIMESTAMPTZ,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # ── inspector_requests ───────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".inspector_requests (
                id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                branch_id           UUID NOT NULL
                                        REFERENCES "{s}".branches(id) ON DELETE CASCADE,
                inspector_id        UUID
                                        REFERENCES "{s}".users(id) ON DELETE SET NULL,
                request_type        VARCHAR(30) NOT NULL DEFAULT 'add_teacher'
                                        CHECK (request_type IN ('add_teacher','other')),
                first_name          VARCHAR(100) NOT NULL,
                last_name           VARCHAR(100),
                phone               VARCHAR(20),
                subjects            VARCHAR(500),
                salary_type         VARCHAR(20),
                salary_amount       DECIMAL(12,2),
                notes               TEXT,
                status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                                        CHECK (status IN
                                          ('pending','approved','rejected')),
                reviewed_by         UUID
                                        REFERENCES "{s}".users(id) ON DELETE SET NULL,
                reject_reason       TEXT,
                reviewed_at         TIMESTAMPTZ,
                created_teacher_id  UUID
                                        REFERENCES "{s}".teachers(id) ON DELETE SET NULL,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # ── Indekslar ────────────────────────────────────────────────
        tag = s[-8:].replace("-", "_")
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_users_branch_{tag}
            ON "{s}".users (branch_id)
            WHERE branch_id IS NOT NULL
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_expenses_branch_{tag}
            ON "{s}".branch_expenses (branch_id, status)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_insp_req_branch_{tag}
            ON "{s}".inspector_requests (branch_id, status)
        """))

        print(f"  ✅ {s}: branches migration done")


def downgrade() -> None:
    conn = op.get_bind()
    schemas = _schemas(conn)

    for s in schemas:
        conn.execute(sa.text(
            f'DROP TABLE IF EXISTS "{s}".inspector_requests CASCADE'
        ))
        conn.execute(sa.text(
            f'DROP TABLE IF EXISTS "{s}".branch_expenses CASCADE'
        ))
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".branches DROP COLUMN IF EXISTS manager_id
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".users DROP COLUMN IF EXISTS branch_id
        """))
        conn.execute(sa.text(f"""
            ALTER TABLE "{s}".users DROP CONSTRAINT IF EXISTS ck_user_role
        """))
