"""
Mavjud invitations jadvaliga promo_text ustunini qo'shish.
Ishlatish: python add_promo_text.py
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
        "SELECT schema_name FROM public.tenants WHERE is_active = true"
    )
    print(f"📋 {len(tenants)} ta tenant")

    for t in tenants:
        s = t["schema_name"]
        print(f"\n🔧 {s}")

        # invitations.promo_text
        try:
            await conn.execute(f"""
                ALTER TABLE "{s}".invitations
                ADD COLUMN IF NOT EXISTS promo_text TEXT
            """)
            print("  ✅ invitations.promo_text qo'shildi")
        except Exception as e:
            print(f"  ⚠️  invitations: {e}")

        # certificates.description — null bo'lishi mumkin
        try:
            await conn.execute(f"""
                ALTER TABLE "{s}".certificates
                ALTER COLUMN description DROP NOT NULL
            """)
        except Exception:
            pass

    await conn.close()
    print("\n🎉 Tayyor!")


if __name__ == "__main__":
    asyncio.run(main())
