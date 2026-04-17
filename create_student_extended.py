"""
Student modeliga yangi maydonlar qo'shish.
Ishlatish: python create_student_extended.py
"""
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

DB_URL = os.getenv("DATABASE_URL",
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

        await conn.execute(f"""
            ALTER TABLE "{s}".students
            ADD COLUMN IF NOT EXISTS payment_day    SMALLINT DEFAULT 1
                CHECK (payment_day BETWEEN 1 AND 31),
            ADD COLUMN IF NOT EXISTS monthly_fee    DECIMAL(12,2),
            ADD COLUMN IF NOT EXISTS is_approved    BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS pending_delete BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS created_by     UUID
        """)
        print("  ✅ students: payment_day, monthly_fee, is_approved, pending_delete, created_by")

        # telegram maydonlari users jadvalida borligini tekshirish
        cols = await conn.fetch(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = '{s}' AND table_name = 'users'
            AND column_name IN ('telegram_id', 'telegram_username')
        """)
        existing = {r['column_name'] for r in cols}
        if 'telegram_id' not in existing:
            await conn.execute(f"""
                ALTER TABLE "{s}".users ADD COLUMN IF NOT EXISTS telegram_id BIGINT
            """)
            print("  ✅ users: telegram_id qo'shildi")
        if 'telegram_username' not in existing:
            await conn.execute(f"""
                ALTER TABLE "{s}".users ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(100)
            """)
            print("  ✅ users: telegram_username qo'shildi")

    await conn.close()
    print("\n🎉 Tayyor! Keyin: alembic stamp 004_student_extended")


if __name__ == "__main__":
    asyncio.run(main())
