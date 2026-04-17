"""
Inspektor foydalanuvchi yaratish va filiaga tayinlash.
Ishlatish: python create_inspector.py

Bu skript:
1. Yangi user yaratadi (role=inspector)
2. Uni tanlangan filiaga tayinlaydi
3. branches.manager_id ni yangilaydi
"""
import asyncio
import os
import uuid

import asyncpg
import bcrypt
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://edusaas:edusaas_pass@localhost:5432/edusaas"
).replace("postgresql+asyncpg://", "postgresql://")

# ── O'zgartiring ──────────────────────────────────────────────────────
TENANT_SLUG   = "demo-markaz"       # tenant slug
FIRST_NAME    = "Inspektor 2"         # ismi
LAST_NAME     = "Test 2"              # familiyasi
EMAIL         = "inspektor2@demo.uz" # login email
PHONE         = "+998901234568"     # telefon
PASSWORD      = "Inspektor123!"     # parol
BRANCH_NAME   = None                # None = birinchi filialga tayinlash
                                    # yoki: "Chilonzor filiali"
# ─────────────────────────────────────────────────────────────────────


async def main():
    conn = await asyncpg.connect(DB_URL)

    # Schema
    schema = f"tenant_{TENANT_SLUG.replace('-', '_')}"
    await conn.execute(f'SET search_path TO "{schema}", public')

    # Filiallarni ko'rish
    branches = await conn.fetch(f'SELECT id, name, is_main FROM "{schema}".branches WHERE is_active = true')

    if not branches:
        print("❌ Hali filial yo'q. Avval admin panelida filial yarating.")
        await conn.close()
        return

    print("📋 Mavjud filiallar:")
    for i, b in enumerate(branches):
        main_tag = " (asosiy)" if b["is_main"] else ""
        print(f"  {i+1}. {b['name']}{main_tag} — {b['id']}")

    # Filial tanlash
    if BRANCH_NAME:
        branch = next((b for b in branches if b["name"] == BRANCH_NAME), None)
        if not branch:
            print(f"❌ '{BRANCH_NAME}' nomli filial topilmadi")
            await conn.close()
            return
    else:
        branch = branches[0]
        print(f"\n→ '{branch['name']}' fililiga tayinlanadi")

    branch_id = branch["id"]

    # Email allaqachon bormi?
    existing = await conn.fetchrow(
        f'SELECT id, role FROM "{schema}".users WHERE email = $1', EMAIL
    )

    if existing:
        print(f"\n⚠️  Bu email allaqachon mavjud (role: {existing['role']})")
        print("Mavjud userni inspektonga o'tkazish...")
        user_id = existing["id"]

        await conn.execute(f"""
            UPDATE "{schema}".users
            SET role = 'inspector', branch_id = $1
            WHERE id = $2
        """, branch_id, user_id)
    else:
        # Parol hash
        hashed = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
        user_id = uuid.uuid4()

        await conn.execute(f"""
            INSERT INTO "{schema}".users
                (id, first_name, last_name, email, phone, password_hash,
                 role, branch_id, is_active, is_verified, language_code)
            VALUES ($1,$2,$3,$4,$5,$6,'inspector',$7,true,true,'uz')
        """, user_id, FIRST_NAME, LAST_NAME, EMAIL, PHONE, hashed, branch_id)

        print(f"\n✅ Yangi inspektor yaratildi: {user_id}")

    # Branch manager_id yangilash
    await conn.execute(f"""
        UPDATE "{schema}".branches
        SET manager_id = $1
        WHERE id = $2
    """, user_id, branch_id)

    print(f"""
✅ Tayyor!

Login ma'lumotlari:
  Tenant:   {TENANT_SLUG}
  Email:    {EMAIL}
  Parol:    {PASSWORD}
  Filial:   {branch['name']}
  Role:     inspector

Brauzerda: /login → tenant={TENANT_SLUG}, email={EMAIL}
    """)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())