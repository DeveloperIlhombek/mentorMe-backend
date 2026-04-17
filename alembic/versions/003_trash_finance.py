"""
003_trash_and_finance

Revision ID: 003_trash_finance
Revises: 002_gamification
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_trash_finance"
down_revision: Union[str, None] = "002_gamification"
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
        # ── Trash: deleted_at + deleted_by qo'shish ──────────────
        for table in ("users", "students", "teachers", "groups"):
            conn.execute(sa.text(f"""
                ALTER TABLE "{s}".{table}
                ADD COLUMN IF NOT EXISTS deleted_at  TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS deleted_by  UUID
                    REFERENCES "{s}".users(id) ON DELETE SET NULL
            """))

        # ── Finance: transactions jadvali ────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".finance_transactions (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                type             VARCHAR(10)  NOT NULL
                                     CHECK (type IN ('income','expense')),
                amount           DECIMAL(15,2) NOT NULL CHECK (amount > 0),
                currency         VARCHAR(5)   NOT NULL DEFAULT 'UZS',
                payment_method   VARCHAR(20)  NOT NULL DEFAULT 'cash'
                                     CHECK (payment_method IN ('cash','bank')),
                category         VARCHAR(50)  NOT NULL,
                description      TEXT,
                reference_type   VARCHAR(30),
                reference_id     UUID,
                created_by       UUID REFERENCES "{s}".users(id) ON DELETE SET NULL,
                transaction_date DATE         NOT NULL DEFAULT CURRENT_DATE,
                created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """))

        # ── Finance: kassa holati (snapshot) ─────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{s}".finance_balance (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                cash_amount  DECIMAL(15,2) NOT NULL DEFAULT 0,
                bank_amount  DECIMAL(15,2) NOT NULL DEFAULT 0,
                updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
            )
        """))

        # Default balance row
        conn.execute(sa.text(f"""
            INSERT INTO "{s}".finance_balance (cash_amount, bank_amount)
            SELECT 0, 0
            WHERE NOT EXISTS (SELECT 1 FROM "{s}".finance_balance)
        """))

        # Indekslar
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_finance_date_{s.replace('-','_')}
            ON "{s}".finance_transactions(transaction_date DESC)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_finance_type_{s.replace('-','_')}
            ON "{s}".finance_transactions(type, category)
        """))
        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_finance_ref_{s.replace('-','_')}
            ON "{s}".finance_transactions(reference_type, reference_id)
        """))


def downgrade() -> None:
    conn = op.get_bind()
    for s in _schemas(conn):
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{s}".finance_balance'))
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{s}".finance_transactions'))
        for table in ("users", "students", "teachers", "groups"):
            conn.execute(sa.text(f"""
                ALTER TABLE "{s}".{table}
                DROP COLUMN IF EXISTS deleted_at,
                DROP COLUMN IF EXISTS deleted_by
            """))
