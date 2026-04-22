"""
EduSaaS — Seed Data Script (faqat ma'lumotlar)
================================================
Bu script FAQAT ma'lumot kiritadi — jadvallarni yaratmaydi.

Oldin `alembic upgrade head` ishlatilgan bo'lishi SHART!

Kiritiladi:
  1. Subscription plans (Starter, Pro, Enterprise)
  2. Super Admin tenant + super_admin user (platform schema)
  3. Demo ta'lim markazi + admin user (demo-markaz schema)
  4. Demo o'qituvchilar, guruhlar, o'quvchilar, davomat, to'lovlar

Ishlatish:
  python seed_data.py
"""

import asyncio
import os
import uuid
from datetime import date, datetime, timedelta

import bcrypt
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://edusaas:edusaas_pass@localhost:5432/edusaas"
).replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")


def hp(password: str) -> str:
    """Parolni hash qilish."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def seed():
    try:
        import asyncpg
    except ImportError:
        print("❌  asyncpg topilmadi: pip install asyncpg")
        return

    print("🔌  PostgreSQL ga ulanmoqda...")
    conn = await asyncpg.connect(DB_URL)
    print("✅  Ulandi!\n")

    try:
        await run_seed(conn)
    finally:
        await conn.close()
        print("\n🔌  Ulanish yopildi.")


async def run_seed(conn):
    print("=" * 55)
    print("  EduSaaS Seed Data (faqat users + demo)")
    print("=" * 55)
    print("  ⚠️  Bu skript alembic upgrade head DAN KEYIN ishlaydi!")
    print("=" * 55)

    # ── Tenant schemalarni aniqlash ────────────────────────────
    sa_schema   = "tenant_platform"
    demo_schema = "tenant_demo_markaz"

    # ── 1. Super Admin user ────────────────────────────────────
    print("\n👑  1. Super Admin user...")
    sa_email    = "superadmin@edusaas.uz"
    sa_password = "Admin123!"
    existing_sa = await conn.fetchrow(
        f'SELECT id FROM "{sa_schema}".users WHERE email = $1', sa_email
    )
    if existing_sa:
        print(f"   ⏭  Super admin — mavjud")
    else:
        await conn.execute(
            f"""INSERT INTO "{sa_schema}".users
               (first_name, last_name, email, password_hash, role, phone, is_active, is_verified)
               VALUES ($1,$2,$3,$4,'super_admin',$5,TRUE,TRUE)""",
            "Super", "Admin", sa_email, hp(sa_password), "+998900000000"
        )
        print(f"   ✅  Super Admin: {sa_email} / {sa_password}")

    # ── 2. Demo markaz admin user ──────────────────────────────
    print("\n🏫  2. Demo markaz admin user...")
    admin_email    = "admin@demo-markaz.uz"
    admin_password = "Admin123!"
    existing_adm = await conn.fetchrow(
        f'SELECT id FROM "{demo_schema}".users WHERE email = $1', admin_email
    )
    if existing_adm:
        print(f"   ⏭  Admin user — mavjud")
    else:
        await conn.execute(
            f"""INSERT INTO "{demo_schema}".users
               (first_name, last_name, email, password_hash, role, phone, is_active, is_verified)
               VALUES ($1,$2,$3,$4,'admin',$5,TRUE,TRUE)""",
            "Alisher", "Toshmatov", admin_email, hp(admin_password), "+998901111111"
        )
        print(f"   ✅  Admin: {admin_email} / {admin_password}")

    # ── 3. Demo ma'lumotlar ────────────────────────────────────
    print(f"\n🌱  3. Demo ma'lumotlar ({demo_schema})...")
    await seed_demo(conn, demo_schema)

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  ✅  SEED MUVAFFAQIYATLI TUGADI!")
    print("=" * 55)
    print("""
  📊  Login ma'lumotlari:
  ┌────────────────────────────────────────────────┐
  │  🔑  SUPER ADMIN                               │
  │      Tenant  : platform                        │
  │      Email   : superadmin@edusaas.uz           │
  │      Parol   : Admin123!                       │
  ├────────────────────────────────────────────────┤
  │  🔑  ADMIN (Demo markaz)                       │
  │      Tenant  : demo-markaz                     │
  │      Email   : admin@demo-markaz.uz            │
  │      Parol   : Admin123!                       │
  ├────────────────────────────────────────────────┤
  │  O'qituvchilar barcha: Teacher123!             │
  │  O'quvchilar barcha:   Student123!             │
  └────────────────────────────────────────────────┘

  🚀  Login: http://localhost:3000/uz/login
    """)


async def seed_demo(conn, schema: str):
    """Demo markaz uchun branch, teacher, group, student, attendance, payment."""
    import json

    # Branch
    existing_b = await conn.fetchrow(
        f'SELECT id FROM "{schema}".branches WHERE is_main = TRUE LIMIT 1'
    )
    if existing_b:
        branch_id = str(existing_b["id"])
        print(f"   ⏭  Filial — mavjud")
    else:
        row = await conn.fetchrow(
            f"""INSERT INTO "{schema}".branches (name, address, phone, is_main)
               VALUES ($1,$2,$3,TRUE) RETURNING id""",
            "Asosiy filial", "Toshkent, Yunusobod, Amir Temur 15", "+998712345678"
        )
        branch_id = str(row["id"])
        print(f"   ✅  Asosiy filial")

    # Teachers
    teachers_data = [
        ("Aziz",    "Toshev",    "aziz@demo-markaz.uz",    "+998901234561", ["Ingliz tili"], "percent", 15),
        ("Malika",  "Yusupova",  "malika@demo-markaz.uz",  "+998901234562", ["Ingliz tili"], "fixed",   2500000),
        ("Bobur",   "Karimov",   "bobur@demo-markaz.uz",   "+998901234563", ["Matematika"],  "fixed",   2000000),
        ("Nargiza", "Rahimova",  "nargiza@demo-markaz.uz", "+998901234564", ["Rus tili"],    "per_lesson", 80000),
    ]
    teacher_ids = []
    for fn, ln, email, phone, subjects, sal_type, sal_amount in teachers_data:
        existing_t = await conn.fetchrow(
            f"""SELECT t.id FROM "{schema}".teachers t
                JOIN "{schema}".users u ON u.id = t.user_id
                WHERE u.email = $1""", email
        )
        if existing_t:
            teacher_ids.append(str(existing_t["id"]))
        else:
            u_row = await conn.fetchrow(
                f"""INSERT INTO "{schema}".users
                   (first_name, last_name, email, password_hash, role, phone, is_active, is_verified)
                   VALUES ($1,$2,$3,$4,'teacher',$5,TRUE,TRUE) RETURNING id""",
                fn, ln, email, hp("Teacher123!"), phone
            )
            t_row = await conn.fetchrow(
                f"""INSERT INTO "{schema}".teachers
                   (user_id, branch_id, subjects, salary_type, salary_amount, hired_at, is_approved)
                   VALUES ($1,$2,$3,$4,$5,$6,TRUE) RETURNING id""",
                str(u_row["id"]), branch_id, subjects, sal_type, sal_amount,
                date(2024, 9, 1)
            )
            teacher_ids.append(str(t_row["id"]))
    print(f"   ✅  {len(teacher_ids)} ta o'qituvchi")

    # Groups
    groups_data = [
        ("IELTS B2 — 1-guruh", "Ingliz tili", "B2", 0, 500000, 15,
         [{"day":1,"start":"09:00","end":"11:00"},{"day":3,"start":"09:00","end":"11:00"},{"day":5,"start":"09:00","end":"11:00"}]),
        ("Ingliz tili A2",     "Ingliz tili", "A2", 1, 350000, 15,
         [{"day":2,"start":"11:00","end":"13:00"},{"day":4,"start":"11:00","end":"13:00"}]),
        ("Matematika 9-sinf",  "Matematika",  "9-sinf", 2, 400000, 12,
         [{"day":1,"start":"14:00","end":"16:00"},{"day":3,"start":"14:00","end":"16:00"}]),
        ("Rus tili B1",        "Rus tili",    "B1", 3, 300000, 12,
         [{"day":2,"start":"16:00","end":"18:00"},{"day":5,"start":"16:00","end":"18:00"}]),
        ("IELTS B1 — 1-guruh", "Ingliz tili", "B1", 0, 450000, 15,
         [{"day":1,"start":"17:00","end":"19:00"},{"day":3,"start":"17:00","end":"19:00"},{"day":5,"start":"17:00","end":"19:00"}]),
    ]
    group_ids = []
    for gname, subj, level, tidx, fee, maxst, sched in groups_data:
        existing_g = await conn.fetchrow(
            f'SELECT id FROM "{schema}".groups WHERE name = $1', gname
        )
        if existing_g:
            group_ids.append(str(existing_g["id"]))
        else:
            g_row = await conn.fetchrow(
                f"""INSERT INTO "{schema}".groups
                   (name, branch_id, teacher_id, subject, level, schedule, start_date, monthly_fee, max_students, status)
                   VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,'active') RETURNING id""",
                gname, branch_id, teacher_ids[tidx % len(teacher_ids)],
                subj, level, json.dumps(sched), date(2026, 1, 15), fee, maxst
            )
            group_ids.append(str(g_row["id"]))
    print(f"   ✅  {len(group_ids)} ta guruh")

    # Students
    students_raw = [
        ("Ali",      "Karimov",    "ali@gmail.com",       "+998901000001", date(2007,3,15),  "male",   150000,  0),
        ("Zulfiya",  "Rahimova",   "zulfiya@gmail.com",   "+998901000002", date(2008,7,22),  "female", -50000,  1),
        ("Bobur",    "Toshmatov",  "bobur_s@gmail.com",   "+998901000003", date(2006,11,5),  "male",   0,       2),
        ("Nilufar",  "Yusupova",   "nilufar@gmail.com",   "+998901000004", date(2009,2,18),  "female", 200000,  1),
        ("Jasur",    "Mirzayev",   "jasur@gmail.com",     "+998901000005", date(2007,8,30),  "male",   -120000, 4),
        ("Dilorom",  "Hasanova",   "dilorom@gmail.com",   "+998901000006", date(2008,4,12),  "female", 50000,   0),
        ("Sardor",   "Ergashev",   "sardor_s@gmail.com",  "+998901000007", date(2006,9,25),  "male",   0,       3),
        ("Mohira",   "Qodirov",    "mohira@gmail.com",    "+998901000008", date(2009,1,7),   "female", 350000,  2),
        ("Sherzod",  "Nazarov",    "sherzod@gmail.com",   "+998901000009", date(2007,6,14),  "male",   0,       4),
        ("Feruza",   "Tojiboyeva", "feruza@gmail.com",    "+998901000010", date(2008,12,3),  "female", -80000,  1),
    ]
    student_ids = []
    student_group_map = []
    for fn, ln, email, phone, dob, gender, balance, gidx in students_raw:
        existing_s = await conn.fetchrow(
            f"""SELECT s.id FROM "{schema}".students s
                JOIN "{schema}".users u ON u.id = s.user_id
                WHERE u.email = $1""", email
        )
        if existing_s:
            student_ids.append(str(existing_s["id"]))
            student_group_map.append((str(existing_s["id"]), gidx))
        else:
            u_row = await conn.fetchrow(
                f"""INSERT INTO "{schema}".users
                   (first_name, last_name, email, password_hash, role, phone, is_active, is_verified)
                   VALUES ($1,$2,$3,$4,'student',$5,TRUE,TRUE) RETURNING id""",
                fn, ln, email, hp("Student123!"), phone
            )
            s_row = await conn.fetchrow(
                f"""INSERT INTO "{schema}".students
                   (user_id, branch_id, date_of_birth, gender, balance, is_active, is_approved)
                   VALUES ($1,$2,$3,$4,$5,TRUE,TRUE) RETURNING id""",
                str(u_row["id"]), branch_id, dob, gender, balance
            )
            sid = str(s_row["id"])
            student_ids.append(sid)
            student_group_map.append((sid, gidx))
            # Gamification profile
            await conn.execute(
                f"""INSERT INTO "{schema}".gamification_profiles
                   (student_id, total_xp, current_level, weekly_xp)
                   VALUES ($1,0,1,0) ON CONFLICT DO NOTHING""",
                sid
            )

    # Assign to groups
    for sid, gidx in student_group_map:
        if gidx < len(group_ids):
            await conn.execute(
                f"""INSERT INTO "{schema}".student_groups (student_id, group_id, joined_at)
                   VALUES ($1,$2,$3) ON CONFLICT DO NOTHING""",
                sid, group_ids[gidx], date(2026, 1, 15)
            )
    print(f"   ✅  {len(student_ids)} ta o'quvchi")

    # Attendance (so'nggi 7 kun)
    att_count = 0
    for i in range(7):
        att_date = date.today() - timedelta(days=i)
        if att_date.weekday() >= 5:
            continue
        for j, (sid, gidx) in enumerate(student_group_map[:8]):
            if gidx >= len(group_ids): continue
            status = "absent" if (i == 2 and j % 3 == 0) else "late" if (j % 5 == 0) else "present"
            try:
                tid = teacher_ids[gidx % len(teacher_ids)]
                await conn.execute(
                    f"""INSERT INTO "{schema}".attendance
                       (student_id, group_id, teacher_id, date, status)
                       VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING""",
                    sid, group_ids[gidx], tid, att_date, status
                )
                att_count += 1
            except Exception:
                pass
    print(f"   ✅  Davomat: {att_count} ta yozuv")

    # Payments
    pay_count = 0
    for j, (sid, gidx) in enumerate(student_group_map):
        if gidx >= len(group_ids): continue
        amount = groups_data[gidx][4]
        method = "click" if j % 2 == 0 else "cash"
        try:
            await conn.execute(
                f"""INSERT INTO "{schema}".payments
                   (student_id, group_id, amount, payment_method, status, period_month, period_year, paid_at)
                   VALUES ($1,$2,$3,$4,'completed',$5,$6,$7)""",
                sid, group_ids[gidx], amount, method,
                4, 2026,
                datetime.now() - timedelta(days=j)
            )
            pay_count += 1
        except Exception:
            pass
    print(f"   ✅  To'lovlar: {pay_count} ta")


if __name__ == "__main__":
    asyncio.run(seed())
