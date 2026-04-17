"""
Demo foydalanuvchilar yaratish — barcha rollar uchun.
Ishlatish: python create_demo_users.py
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

TENANT_SLUG = "demo-markaz"

USERS = [
    {
        "first_name":    "Sardor",
        "last_name":     "Toshmatov",
        "email":         "teacher@demo-markaz.uz",
        "phone":         "+998901111111",
        "password":      "Teacher123!",
        "role":          "teacher",
        "subjects":      ["Ingliz tili", "IELTS"],
        "salary_type":   "fixed",
        "salary_amount": 2_500_000,
    },
    {
        "first_name":    "Jasur",
        "last_name":     "Aliyev",
        "email":         "student@demo-markaz.uz",
        "phone":         "+998902222222",
        "password":      "Student123!",
        "role":          "student",
    },
    {
        "first_name":    "Malika",
        "last_name":     "Nazarova",
        "email":         "parent@demo-markaz.uz",
        "phone":         "+998903333333",
        "password":      "Parent123!",
        "role":          "parent",
    },
    {
        "first_name":    "Dilnoza",
        "last_name":     "Yusupova",
        "email":         "inspektor@demo.uz",
        "phone":         "+998904444444",
        "password":      "Inspektor123!",
        "role":          "inspector",
    },
]


def hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def main():
    conn = await asyncpg.connect(DB_URL)
    schema = f"tenant_{TENANT_SLUG.replace('-', '_')}"
    await conn.execute(f'SET search_path TO "{schema}", public')

    # Avval mavjud filialni olish (inspektor uchun)
    branches = await conn.fetch(f'SELECT id, name FROM "{schema}".branches LIMIT 1')
    branch_id = branches[0]["id"] if branches else None
    print(f"📋 Filial: {branches[0]['name'] if branches else 'Yo`q'}")

    for u in USERS:
        # Mavjud email tekshirish
        existing = await conn.fetchrow(
            f'SELECT id, role FROM "{schema}".users WHERE email = $1', u["email"]
        )
        if existing:
            print(f"⚠️  {u['email']} allaqachon mavjud (role: {existing['role']}) — o'tkazib yuborildi")
            continue

        user_id   = uuid.uuid4()
        hashed    = hash_pw(u["password"])
        branch_fk = branch_id if u["role"] in ("inspector", "teacher") else None

        # User yaratish
        await conn.execute(f"""
            INSERT INTO "{schema}".users
                (id, first_name, last_name, email, phone, password_hash,
                 role, branch_id, is_active, is_verified, language_code)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,true,true,'uz')
        """, user_id, u["first_name"], u["last_name"],
             u["email"], u["phone"], hashed,
             u["role"], branch_fk)

        print(f"✅ {u['role']:10} — {u['email']}")

        # Teacher uchun teachers jadvaliga yozish
        if u["role"] == "teacher":
            teacher_id = uuid.uuid4()
            await conn.execute(f"""
                INSERT INTO "{schema}".teachers
                    (id, user_id, branch_id, subjects,
                     salary_type, salary_amount, is_active)
                VALUES ($1,$2,$3,$4,$5,$6,true)
            """, teacher_id, user_id, branch_id,
                 u.get("subjects", []),
                 u.get("salary_type", "fixed"),
                 u.get("salary_amount", 0))
            print(f"   └─ teachers jadvali yozildi (id: {teacher_id})")

        # Student uchun students jadvaliga yozish
        if u["role"] == "student":
            student_id = uuid.uuid4()
            await conn.execute(f"""
                INSERT INTO "{schema}".students
                    (id, user_id, branch_id, balance, is_active, enrolled_at)
                VALUES ($1,$2,$3,0,true,CURRENT_DATE)
            """, student_id, user_id, branch_id)
            print(f"   └─ students jadvali yozildi (id: {student_id})")

        # Inspector uchun branch.manager_id yangilash
        if u["role"] == "inspector" and branch_id:
            await conn.execute(f"""
                UPDATE "{schema}".branches SET manager_id = $1 WHERE id = $2
            """, user_id, branch_id)
            print(f"   └─ branches.manager_id yangilandi")

    await conn.close()
    print(f"""
🎉 Tayyor! Login ma'lumotlari:

  Tenant slug: {TENANT_SLUG}

  👨‍🏫 O'qituvchi:  teacher@demo-markaz.uz  / Teacher123!
  🎓  O'quvchi:    student@demo-markaz.uz   / Student123!
  👨‍👩‍👧 Ota-ona:     parent@demo-markaz.uz    / Parent123!
  🔍  Inspektor:   inspektor@demo.uz         / Inspektor123!
    """)


if __name__ == "__main__":
    asyncio.run(main())