"""
EduSaaS — Database Full Reset Script
======================================
Bu script barcha ma'lumotlarni va schemalarni to'liq o'chiradi.

To'liq tartib (TO'LIQROG'I - 5 QADAM):
  1. python reset_db.py       ← bu fayl (barcha schemalar o'chadi)
  2. alembic upgrade head     ← public jadvallarni yaratadi (tenants bo'sh)
  3. python seed_tenants.py   ← tenant yozuvlari + alembic_version → 001_initial
  4. alembic upgrade head     ← YANA ISHLATILADI (tenant schemalar yaratiladi!)
  5. python seed_data.py      ← users + demo data kiritiladi

Ishlatish:
  python reset_db.py
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://edusaas:edusaas_pass@localhost:5432/edusaas"
).replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")


async def reset():
    try:
        import asyncpg
    except ImportError:
        print("❌  asyncpg topilmadi: pip install asyncpg")
        return

    print("🔌  PostgreSQL ga ulanmoqda...")
    conn = await asyncpg.connect(DB_URL)
    print("✅  Ulandi!\n")

    try:
        await drop_all(conn)
        print("""
╔══════════════════════════════════════════════════════╗
║  ✅  DATABASE TO'LIQ O'CHIRILDI!                     ║
║                                                      ║
║  Endi quyidagilarni ketma-ket bajaring:              ║
║                                                      ║
║  1. alembic upgrade head                             ║
║     (barcha jadvallarni qayta yaratadi)               ║
║                                                      ║
║  2. python seed_data.py                              ║
║     (superadmin, admin va demo ma'lumotlar kiradi)   ║
╚══════════════════════════════════════════════════════╝
        """)
    finally:
        await conn.close()
        print("🔌  Ulanish yopildi.")


async def drop_all(conn):
    print("🗑   Barcha tenant schemalar o'chirilmoqda...")

    # 1. Barcha tenant schemalarini topish va o'chirish
    schemas = await conn.fetch("""
        SELECT schema_name FROM information_schema.schemata
        WHERE schema_name LIKE 'tenant_%'
    """)
    for row in schemas:
        schema = row["schema_name"]
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        print(f"   🗑  '{schema}' o'chirildi")

    # 2. Public jadvallarni DROP qilish (TRUNCATE emas — alembic qayta yarataolsin)
    print("\n🗑   Public schema jadvallar o'chirilmoqda...")
    for tbl in ["public.tenants", "public.subscription_plans"]:
        await conn.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
        print(f"   🗑  {tbl} o'chirildi")

    # 3. Alembic version — MUHIM: o'chirilmasa migration qayta ishlamaydi
    print("\n🗑   Alembic version tozalanmoqda...")
    await conn.execute("DROP TABLE IF EXISTS public.alembic_version CASCADE")
    print("   🗑  alembic_version o'chirildi")

    print("\n✅  Barcha schemalar va jadvallar o'chirildi!")


if __name__ == "__main__":
    print("=" * 55)
    print("  ⚠️   EduSaaS — Database Full Reset")
    print("=" * 55)
    print("\nBu amal BARCHA ma'lumotlar va jadvallarni o'chiradi!")
    print("Qayta tiklash uchun alembic + seed_data.py ishlatiladi.\n")

    confirm = input("Davom etish uchun 'TASDIQLASH' deb yozing: ")
    if confirm.strip().upper() != "TASDIQLASH":
        print("❌  Bekor qilindi.")
    else:
        asyncio.run(reset())
