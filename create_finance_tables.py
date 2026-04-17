"""Moliya va trash jadvallarini yaratish. Ishlatish: python create_finance_tables.py"""
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

DB_URL = os.getenv("DATABASE_URL","postgresql+asyncpg://edusaas:edusaas_pass@localhost:5432/edusaas").replace("postgresql+asyncpg://","postgresql://")

async def main():
    conn = await asyncpg.connect(DB_URL)
    tenants = await conn.fetch("SELECT schema_name FROM public.tenants WHERE is_active = true")
    print(f"📋 {len(tenants)} ta tenant")
    for t in tenants:
        s = t["schema_name"]
        print(f"\n🔧 {s}")
        # Trash columns
        for table in ("students", "teachers", "groups", "users"):
            try:
                await conn.execute(f'ALTER TABLE "{s}".{table} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ')
                await conn.execute(f'ALTER TABLE "{s}".{table} ADD COLUMN IF NOT EXISTS deleted_by UUID')
            except Exception as e:
                print(f"  ⚠️  {table}: {e}")
        print("  ✅ trash columns")
        # Finance
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".finance_transactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                type VARCHAR(10) NOT NULL CHECK (type IN ('income','expense')),
                amount DECIMAL(15,2) NOT NULL CHECK (amount > 0),
                currency VARCHAR(5) NOT NULL DEFAULT 'UZS',
                payment_method VARCHAR(20) NOT NULL DEFAULT 'cash' CHECK (payment_method IN ('cash','bank')),
                category VARCHAR(50) NOT NULL,
                description TEXT,
                reference_type VARCHAR(30),
                reference_id UUID,
                created_by UUID,
                transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".finance_balance (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                cash_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
                bank_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(f"""
            INSERT INTO "{s}".finance_balance (cash_amount, bank_amount)
            SELECT 0, 0 WHERE NOT EXISTS (SELECT 1 FROM "{s}".finance_balance)
        """)
        print("  ✅ finance tables")
    await conn.close()
    print("\n🎉 Tayyor! Keyin: alembic stamp 003_trash_finance")

asyncio.run(main())
