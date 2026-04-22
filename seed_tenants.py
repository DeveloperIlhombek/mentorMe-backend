"""
EduSaaS — Step 2: public.tenants + alembic_version reset.

Alembic tenant schemalarni yaratishi uchun avval bu skript ishlashi kerak.

Tartib:
  1. python reset_db.py
  2. alembic upgrade head     ← public jadvallarni yaratadi (tenants bo'sh)
  3. python seed_tenants.py   ← bu fayl (tenants kiritadi + alembic reset)
  4. alembic upgrade head     ← YANA (endi tenant schemalarni yaratadi!)
  5. python seed_data.py

MUHIM: seed_tenants.py alembic_version ni '001_initial' ga qaytaradi.
Shuning uchun 4-qadamda alembic 002-008 migratsiyalarini qayta ishlatadi —
bu safar public.tenants to'la bo'lgani uchun tenant schemalar yaratiladi.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://edusaas:edusaas_pass@localhost:5432/edusaas"
).replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")


async def seed_tenants():
    import asyncpg
    print("🔌  Ulanmoqda...")
    conn = await asyncpg.connect(DB_URL)

    try:
        # ── Subscription plans ─────────────────────────────────
        plans = [
            ("starter",    "Starter",    199000, 50,   5,   1,
             '{"gamification":true,"ai":false,"white_label":false,"sms":false}'),
            ("pro",        "Pro",        499000, 200,  20,  3,
             '{"gamification":true,"ai":false,"white_label":false,"sms":true}'),
            ("enterprise", "Enterprise", 999000, None, None, None,
             '{"gamification":true,"ai":true,"white_label":true,"sms":true}'),
        ]
        plan_ids = {}
        for slug, name, price, ms, mt, mb, feat in plans:
            row = await conn.fetchrow(
                """INSERT INTO public.subscription_plans
                   (slug, name, price_monthly, max_students, max_teachers, max_branches, features)
                   VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)
                   ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name
                   RETURNING id""",
                slug, name, price, ms, mt, mb, feat
            )
            plan_ids[slug] = str(row["id"])
            print(f"   ✅  Plan: {name}")

        # ── Platform tenant (super admin) ──────────────────────
        row = await conn.fetchrow(
            """INSERT INTO public.tenants
               (slug, name, schema_name, plan_id, subscription_status, brand_color, trial_ends_at)
               VALUES ('platform','EduSaaS Platform','tenant_platform',$1,'active','#3B82F6',
                       NOW() + INTERVAL '9999 days')
               ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name
               RETURNING id""",
            plan_ids["enterprise"]
        )
        print(f"   ✅  Tenant: platform (id={row['id']})")

        # ── Demo markaz tenant ─────────────────────────────────
        row = await conn.fetchrow(
            """INSERT INTO public.tenants
               (slug, name, schema_name, plan_id, subscription_status, brand_color,
                phone, address, trial_ends_at)
               VALUES ('demo-markaz','Al-Xorazm Academy','tenant_demo_markaz',$1,
                       'trial','#3B82F6','+998712345678','Toshkent, Yunusobod',
                       NOW() + INTERVAL '14 days')
               ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name
               RETURNING id""",
            plan_ids["pro"]
        )
        print(f"   ✅  Tenant: demo-markaz (id={row['id']})")

        # ── alembic_version ni 001_initial ga qaytarish ────────
        # Sabab: alembic upgrade head avval bo'sh tenants bilan ishlagan,
        # shuning uchun 002-008 migratsiyalar tenant schemalar yaratmagan.
        # Endi tenants to'la — 002-008 ni qayta ishlatish kerak.
        version_row = await conn.fetchrow(
            "SELECT version_num FROM public.alembic_version LIMIT 1"
        )
        if version_row:
            current = version_row["version_num"]
            if current != "001_initial":
                await conn.execute(
                    "UPDATE public.alembic_version SET version_num = '001_initial'"
                )
                print(f"\n⚙️  alembic_version: {current} → 001_initial")
                print("   (002-008 migratsiyalar tenant schemalar yaratadi)")
            else:
                print("\n⚙️  alembic_version allaqachon 001_initial")
        else:
            print("\n⚠️  alembic_version jadvali topilmadi — avval 'alembic upgrade head' ishlatib ko'ring")

        print("""
✅  Tenant yozuvlari yaratildi!

Endi quyidagilarni bajaring:

  alembic upgrade head   ← tenant schemalarni yaratadi
  python seed_data.py    ← users + demo data kiritadi
""")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed_tenants())
