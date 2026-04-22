"""
EduSaaS — Database Seed Script
================================
Bu script quyidagilarni yaratadi:
  1. Subscription plans (Starter, Pro, Enterprise)
  2. Super Admin tenant + super_admin user
  3. Demo ta'lim markazi (tenant) + admin user
  4. Demo ma'lumotlar: o'qituvchilar, guruhlar, o'quvchilar

Ishlatish:
  pip install asyncpg bcrypt python-dotenv
  python seed.py

Yoki .env fayli bo'lsa:
  DATABASE_URL=postgresql+asyncpg://... python seed.py
"""

import asyncio
import os
import uuid
from datetime import date, datetime, timedelta

import bcrypt
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG ────────────────────────────────────────────────────────────
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://edusaas:edusaas_pass@localhost:5432/edusaas"
).replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def gen_id() -> str:
    return str(uuid.uuid4())


# ── MAIN ──────────────────────────────────────────────────────────────
async def seed():
    try:
        import asyncpg
    except ImportError:
        print("❌  asyncpg topilmadi. O'rnatish: pip install asyncpg")
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
    print("  EduSaaS Seed Script")
    print("=" * 55)

    # ── 1. PUBLIC SCHEMA ──────────────────────────────────────────
    print("\n📦  1. Public schema yaratilmoqda...")

    await conn.execute("""
        CREATE SCHEMA IF NOT EXISTS public;
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.subscription_plans (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR(50)  NOT NULL,
            slug            VARCHAR(30)  NOT NULL UNIQUE,
            price_monthly   INTEGER      NOT NULL DEFAULT 0,
            max_students    INTEGER,
            max_teachers    INTEGER,
            max_branches    INTEGER      DEFAULT 1,
            features        JSONB        DEFAULT '{}',
            is_active       BOOLEAN      DEFAULT TRUE,
            created_at      TIMESTAMPTZ  DEFAULT NOW()
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.tenants (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug                VARCHAR(50)  NOT NULL UNIQUE,
            name                VARCHAR(200) NOT NULL,
            schema_name         VARCHAR(60)  NOT NULL UNIQUE,
            owner_telegram_id   BIGINT,
            phone               VARCHAR(20),
            address             TEXT,
            logo_url            TEXT,
            plan_id             UUID REFERENCES public.subscription_plans(id),
            subscription_status VARCHAR(20)  DEFAULT 'trial',
            trial_ends_at       TIMESTAMPTZ  DEFAULT NOW() + INTERVAL '14 days',
            click_merchant_id   VARCHAR(100),
            click_service_id    VARCHAR(100),
            bot_token           TEXT,
            bot_username        VARCHAR(100),
            custom_domain       VARCHAR(200),
            brand_color         VARCHAR(7)   DEFAULT '#3B82F6',
            is_active           BOOLEAN      DEFAULT TRUE,
            created_at          TIMESTAMPTZ  DEFAULT NOW(),
            updated_at          TIMESTAMPTZ  DEFAULT NOW()
        );
    """)
    print("   ✅  Jadvallar mavjud/yaratildi")

    # ── 2. SUBSCRIPTION PLANS ─────────────────────────────────────
    print("\n📋  2. Tarif rejalari...")

    plans = [
        {
            "slug": "starter",
            "name": "Starter",
            "price_monthly": 199000,
            "max_students": 50,
            "max_teachers": 5,
            "max_branches": 1,
            "features": '{"gamification": true, "ai": false, "white_label": false, "sms": false}',
        },
        {
            "slug": "pro",
            "name": "Pro",
            "price_monthly": 499000,
            "max_students": 200,
            "max_teachers": 20,
            "max_branches": 3,
            "features": '{"gamification": true, "ai": false, "white_label": false, "sms": true}',
        },
        {
            "slug": "enterprise",
            "name": "Enterprise",
            "price_monthly": 999000,
            "max_students": None,
            "max_teachers": None,
            "max_branches": None,
            "features": '{"gamification": true, "ai": true, "white_label": true, "sms": true}',
        },
    ]

    plan_ids = {}
    for p in plans:
        existing = await conn.fetchrow(
            "SELECT id FROM public.subscription_plans WHERE slug = $1", p["slug"]
        )
        if existing:
            plan_ids[p["slug"]] = str(existing["id"])
            print(f"   ⏭  {p['name']} — mavjud")
        else:
            row = await conn.fetchrow(
                """
                INSERT INTO public.subscription_plans
                    (slug, name, price_monthly, max_students, max_teachers, max_branches, features)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                RETURNING id
                """,
                p["slug"], p["name"], p["price_monthly"],
                p["max_students"], p["max_teachers"], p["max_branches"], p["features"],
            )
            plan_ids[p["slug"]] = str(row["id"])
            print(f"   ✅  {p['name']} — yaratildi")

    # ── 3. SUPER ADMIN TENANT ─────────────────────────────────────
    print("\n👑  3. Super Admin tenant...")

    sa_slug = "platform"
    sa_schema = "tenant_platform"

    existing_tenant = await conn.fetchrow(
        "SELECT id, schema_name FROM public.tenants WHERE slug = $1", sa_slug
    )

    if existing_tenant:
        sa_tenant_id = str(existing_tenant["id"])
        sa_schema = existing_tenant["schema_name"]
        print(f"   ⏭  Tenant '{sa_slug}' — mavjud")
    else:
        row = await conn.fetchrow(
            """
            INSERT INTO public.tenants
                (slug, name, schema_name, plan_id, subscription_status, trial_ends_at)
            VALUES ($1, $2, $3, $4, 'active', NOW() + INTERVAL '9999 days')
            RETURNING id
            """,
            sa_slug, "EduSaaS Platform", sa_schema,
            plan_ids["enterprise"],
        )
        sa_tenant_id = str(row["id"])
        print(f"   ✅  Tenant 'platform' — yaratildi")

    # Create tenant schema
    await create_tenant_schema(conn, sa_schema)

    # Super admin user
    sa_email = "superadmin@edusaas.uz"
    sa_password = "Admin123!"

    existing_user = await conn.fetchrow(
        f'SELECT id FROM {sa_schema}.users WHERE email = $1', sa_email
    )
    if existing_user:
        print(f"   ⏭  Super admin — mavjud ({sa_email})")
    else:
        await conn.execute(
            f"""
            INSERT INTO {sa_schema}.users
                (first_name, last_name, email, password_hash, role, phone, is_active, is_verified)
            VALUES ($1, $2, $3, $4, $5, $6, TRUE, TRUE)
            """,
            "Super", "Admin", sa_email, hash_password(sa_password),
            "super_admin", "+998900000000",
        )
        print(f"   ✅  Super admin yaratildi:")
        print(f"       📧  Email    : {sa_email}")
        print(f"       🔑  Parol    : {sa_password}")
        print(f"       👑  Rol      : super_admin")

    # ── 4. DEMO TENANT ────────────────────────────────────────────
    print("\n🏫  4. Demo ta'lim markazi...")

    demo_slug   = "demo-markaz"
    demo_schema = "tenant_demo_markaz"

    existing_demo = await conn.fetchrow(
        "SELECT id FROM public.tenants WHERE slug = $1", demo_slug
    )

    if existing_demo:
        demo_tenant_id = str(existing_demo["id"])
        print(f"   ⏭  Demo markaz — mavjud")
    else:
        row = await conn.fetchrow(
            """
            INSERT INTO public.tenants
                (slug, name, schema_name, plan_id, subscription_status,
                 phone, address, brand_color, trial_ends_at)
            VALUES ($1, $2, $3, $4, 'trial', $5, $6, $7, NOW() + INTERVAL '14 days')
            RETURNING id
            """,
            demo_slug, "Al-Xorazm Academy", demo_schema,
            plan_ids["pro"], "+998712345678",
            "Toshkent, Yunusobod t., Amir Temur ko'chasi 15", "#3B82F6",
        )
        demo_tenant_id = str(row["id"])
        print(f"   ✅  'Al-Xorazm Academy' yaratildi")

    await create_tenant_schema(conn, demo_schema)
    await seed_demo_data(conn, demo_schema, plan_ids)


async def create_tenant_schema(conn, schema: str):
    """Tenant schemasi va barcha jadvallarni yaratish"""
    print(f"\n   🗄  Schema '{schema}' tayyorlanmoqda...")

    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")

    # Users
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.users (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_id      BIGINT UNIQUE,
            telegram_username VARCHAR(100),
            email            VARCHAR(200) UNIQUE,
            password_hash    TEXT,
            first_name       VARCHAR(100) NOT NULL,
            last_name        VARCHAR(100),
            phone            VARCHAR(20) UNIQUE,
            role             VARCHAR(20) NOT NULL DEFAULT 'student',
            branch_id        UUID,
            avatar_url       TEXT,
            language_code    VARCHAR(5)  DEFAULT 'uz',
            is_active        BOOLEAN     DEFAULT TRUE,
            is_verified      BOOLEAN     DEFAULT FALSE,
            last_seen_at     TIMESTAMPTZ,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Branches
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.branches (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR(200) NOT NULL,
            address    TEXT,
            phone      VARCHAR(20),
            is_main    BOOLEAN DEFAULT FALSE,
            is_active  BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Teachers
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.teachers (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES {schema}.users(id) ON DELETE CASCADE,
            branch_id       UUID REFERENCES {schema}.branches(id),
            subjects        TEXT[]       DEFAULT '{{}}',
            bio             TEXT,
            salary_type     VARCHAR(20)  DEFAULT 'fixed',
            salary_amount   DECIMAL(12,2) DEFAULT 0,
            hired_at        DATE,
            is_active       BOOLEAN      DEFAULT TRUE,
            is_approved     BOOLEAN      DEFAULT TRUE,
            created_by      UUID,
            created_by_role VARCHAR(20),
            created_at      TIMESTAMPTZ  DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  DEFAULT NOW()
        );
    """)

    # Groups
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.groups (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name         VARCHAR(200) NOT NULL,
            branch_id    UUID REFERENCES {schema}.branches(id),
            teacher_id   UUID REFERENCES {schema}.teachers(id),
            subject      VARCHAR(200) NOT NULL,
            level        VARCHAR(50),
            schedule     JSONB DEFAULT '[]',
            start_date   DATE,
            end_date     DATE,
            monthly_fee  DECIMAL(12,2) DEFAULT 0,
            max_students INTEGER DEFAULT 15,
            status       VARCHAR(20) DEFAULT 'active',
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            updated_at   TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Students
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.students (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        UUID NOT NULL REFERENCES {schema}.users(id) ON DELETE CASCADE,
            branch_id      UUID REFERENCES {schema}.branches(id),
            date_of_birth  DATE,
            gender         VARCHAR(10),
            parent_id      UUID REFERENCES {schema}.users(id),
            parent_phone   VARCHAR(20),
            balance        DECIMAL(12,2) DEFAULT 0,
            enrolled_at    DATE DEFAULT CURRENT_DATE,
            is_active      BOOLEAN DEFAULT TRUE,
            is_approved    BOOLEAN DEFAULT TRUE,
            pending_delete BOOLEAN DEFAULT FALSE,
            payment_day    INTEGER,
            monthly_fee    DECIMAL(12,2),
            created_by     UUID,
            notes          TEXT,
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            updated_at     TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Student groups
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.student_groups (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id UUID NOT NULL REFERENCES {schema}.students(id) ON DELETE CASCADE,
            group_id   UUID NOT NULL REFERENCES {schema}.groups(id)   ON DELETE CASCADE,
            joined_at  DATE DEFAULT CURRENT_DATE,
            left_at    DATE,
            is_active  BOOLEAN DEFAULT TRUE,
            UNIQUE(student_id, group_id)
        );
    """)

    # Attendance
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.attendance (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id       UUID NOT NULL REFERENCES {schema}.students(id),
            group_id         UUID NOT NULL REFERENCES {schema}.groups(id),
            teacher_id       UUID REFERENCES {schema}.teachers(id),
            date             DATE NOT NULL,
            status           VARCHAR(20) DEFAULT 'present',
            arrived_at       TIME,
            note             TEXT,
            parent_notified  BOOLEAN DEFAULT FALSE,
            notified_at      TIMESTAMPTZ,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(student_id, group_id, date)
        );
    """)

    # Payments
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.payments (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id           UUID NOT NULL REFERENCES {schema}.students(id),
            group_id             UUID REFERENCES {schema}.groups(id),
            amount               DECIMAL(12,2) NOT NULL,
            currency             VARCHAR(5)  DEFAULT 'UZS',
            payment_type         VARCHAR(30) DEFAULT 'subscription',
            payment_method       VARCHAR(30) DEFAULT 'cash',
            click_transaction_id VARCHAR(200) UNIQUE,
            click_paydoc_id      VARCHAR(200),
            status               VARCHAR(20) DEFAULT 'completed',
            received_by          UUID REFERENCES {schema}.users(id),
            period_month         INTEGER,
            period_year          INTEGER,
            note                 TEXT,
            paid_at              TIMESTAMPTZ DEFAULT NOW(),
            created_at           TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Gamification
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.gamification_profiles (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            student_id          UUID UNIQUE NOT NULL REFERENCES {schema}.students(id),
            total_xp            INTEGER DEFAULT 0,
            current_level       INTEGER DEFAULT 1,
            current_streak      INTEGER DEFAULT 0,
            max_streak          INTEGER DEFAULT 0,
            last_activity_date  DATE,
            weekly_xp           INTEGER DEFAULT 0,
            weekly_reset_at     TIMESTAMPTZ,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Notifications
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.notifications (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID NOT NULL REFERENCES {schema}.users(id),
            type       VARCHAR(50),
            title      VARCHAR(200),
            body       TEXT NOT NULL,
            data       JSONB DEFAULT '{{}}',
            channel    VARCHAR(20) DEFAULT 'telegram',
            is_read    BOOLEAN DEFAULT FALSE,
            sent_at    TIMESTAMPTZ,
            read_at    TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    print(f"   ✅  Barcha jadvallar tayyor")


async def seed_demo_data(conn, schema: str, plan_ids: dict):
    """Demo ta'lim markazi uchun to'liq ma'lumotlar"""

    print(f"\n🌱  Demo ma'lumotlar to'ldirilmoqda...")

    # ── Admin user ────────────────────────────────────────────────
    admin_email = "admin@demo-markaz.uz"
    admin_password = "Admin123!"

    existing = await conn.fetchrow(
        f"SELECT id FROM {schema}.users WHERE email = $1", admin_email
    )
    if existing:
        admin_user_id = str(existing["id"])
        print(f"   ⏭  Admin user — mavjud")
    else:
        row = await conn.fetchrow(
            f"""
            INSERT INTO {schema}.users
                (first_name, last_name, email, password_hash, role, phone, is_active, is_verified)
            VALUES ($1,$2,$3,$4,$5,$6,TRUE,TRUE) RETURNING id
            """,
            "Alisher", "Toshmatov", admin_email, hash_password(admin_password),
            "admin", "+998901111111"
        )
        admin_user_id = str(row["id"])
        print(f"   ✅  Admin user:")
        print(f"       📧  Email    : {admin_email}")
        print(f"       🔑  Parol    : {admin_password}")
        print(f"       🏢  Markaz   : demo-markaz")
        print(f"       👤  Rol      : admin")

    # ── Branch ────────────────────────────────────────────────────
    existing_branch = await conn.fetchrow(
        f"SELECT id FROM {schema}.branches WHERE is_main = TRUE LIMIT 1"
    )
    if existing_branch:
        branch_id = str(existing_branch["id"])
        print(f"   ⏭  Filial — mavjud")
    else:
        row = await conn.fetchrow(
            f"""
            INSERT INTO {schema}.branches (name, address, phone, is_main)
            VALUES ($1,$2,$3,TRUE) RETURNING id
            """,
            "Asosiy filial", "Toshkent, Yunusobod, Amir Temur 15", "+998712345678"
        )
        branch_id = str(row["id"])
        print(f"   ✅  Asosiy filial yaratildi")

    # ── Teachers ──────────────────────────────────────────────────
    teachers_data = [
        ("Aziz",    "Toshev",    "aziz@demo-markaz.uz",   "+998901234561", ["Ingliz tili"], "percent", 15),
        ("Malika",  "Yusupova",  "malika@demo-markaz.uz", "+998901234562", ["Ingliz tili"], "fixed", 2500000),
        ("Bobur",   "Karimov",   "bobur@demo-markaz.uz",  "+998901234563", ["Matematika"],  "fixed", 2000000),
        ("Nargiza", "Rahimova",  "nargiza@demo-markaz.uz","+998901234564", ["Rus tili"],    "per_lesson", 80000),
    ]

    teacher_ids = []
    for fn, ln, email, phone, subjects, sal_type, sal_amount in teachers_data:
        existing_t = await conn.fetchrow(
            f"SELECT t.id FROM {schema}.teachers t JOIN {schema}.users u ON u.id=t.user_id WHERE u.email=$1",
            email
        )
        if existing_t:
            teacher_ids.append(str(existing_t["id"]))
        else:
            u_row = await conn.fetchrow(
                f"""INSERT INTO {schema}.users (first_name,last_name,email,password_hash,role,phone,is_active,is_verified)
                    VALUES ($1,$2,$3,$4,'teacher',$5,TRUE,TRUE) RETURNING id""",
                fn, ln, email, hash_password("Teacher123!"), phone
            )
            import json
            t_row = await conn.fetchrow(
                f"""INSERT INTO {schema}.teachers (user_id,branch_id,subjects,salary_type,salary_amount,hired_at)
                    VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
                str(u_row["id"]), branch_id, subjects, sal_type, sal_amount,
                date(2024, 9, 1)
            )
            teacher_ids.append(str(t_row["id"]))

    print(f"   ✅  {len(teachers_data)} ta o'qituvchi ({len(teacher_ids)} ta yangi/mavjud)")

    # ── Groups ────────────────────────────────────────────────────
    import json
    groups_data = [
        ("IELTS B2 — 1-guruh", "Ingliz tili", "B2", teacher_ids[0], 500000, 15,
         [{"day":1,"start":"09:00","end":"11:00","room":"201"},
          {"day":3,"start":"09:00","end":"11:00","room":"201"},
          {"day":5,"start":"09:00","end":"11:00","room":"201"}]),
        ("Ingliz tili A2", "Ingliz tili", "A2", teacher_ids[1], 350000, 15,
         [{"day":2,"start":"11:00","end":"13:00","room":"102"},
          {"day":4,"start":"11:00","end":"13:00","room":"102"},
          {"day":6,"start":"11:00","end":"13:00","room":"102"}]),
        ("Matematika 9-sinf", "Matematika", "9-sinf", teacher_ids[2], 400000, 12,
         [{"day":1,"start":"14:00","end":"16:00","room":"301"},
          {"day":3,"start":"14:00","end":"16:00","room":"301"}]),
        ("Rus tili B1", "Rus tili", "B1", teacher_ids[3], 300000, 12,
         [{"day":2,"start":"16:00","end":"18:00","room":"102"},
          {"day":5,"start":"16:00","end":"18:00","room":"102"}]),
        ("IELTS B1 — 1-guruh", "Ingliz tili", "B1", teacher_ids[0], 450000, 15,
         [{"day":1,"start":"17:00","end":"19:00","room":"201"},
          {"day":3,"start":"17:00","end":"19:00","room":"201"},
          {"day":5,"start":"17:00","end":"19:00","room":"201"}]),
    ]

    group_ids = []
    for gname, subj, level, tid, fee, maxst, sched in groups_data:
        existing_g = await conn.fetchrow(
            f"SELECT id FROM {schema}.groups WHERE name=$1", gname
        )
        if existing_g:
            group_ids.append(str(existing_g["id"]))
        else:
            g_row = await conn.fetchrow(
                f"""INSERT INTO {schema}.groups
                    (name,branch_id,teacher_id,subject,level,schedule,start_date,monthly_fee,max_students,status)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,'active') RETURNING id""",
                gname, branch_id, tid, subj, level, json.dumps(sched),
                date(2026, 1, 15), fee, maxst
            )
            group_ids.append(str(g_row["id"]))

    print(f"   ✅  {len(groups_data)} ta guruh")

    # ── Students ──────────────────────────────────────────────────
    students_raw = [
        ("Ali",      "Karimov",    "ali@gmail.com",      "+998901000001", date(2007,3,15), "male",   150000,  0),
        ("Zulfiya",  "Rahimova",   "zulfiya@gmail.com",  "+998901000002", date(2008,7,22), "female", -50000,  1),
        ("Bobur",    "Toshmatov",  "bobur2@gmail.com",   "+998901000003", date(2006,11,5), "male",   0,       2),
        ("Nilufar",  "Yusupova",   "nilufar@gmail.com",  "+998901000004", date(2009,2,18), "female", 200000,  1),
        ("Jasur",    "Mirzayev",   "jasur@gmail.com",    "+998901000005", date(2007,8,30), "male",   -120000, 4),
        ("Dilorom",  "Hasanova",   "dilorom@gmail.com",  "+998901000006", date(2008,4,12), "female", 50000,   0),
        ("Sardor",   "Ergashev",   "sardor@gmail.com",   "+998901000007", date(2006,9,25), "male",   0,       3),
        ("Mohira",   "Qodirov",    "mohira@gmail.com",   "+998901000008", date(2009,1,7),  "female", 350000,  2),
        ("Sherzod",  "Nazarov",    "sherzod@gmail.com",  "+998901000009", date(2007,6,14), "male",   0,       4),
        ("Feruza",   "Tojiboyeva", "feruza@gmail.com",   "+998901000010", date(2008,12,3), "female", -80000,  1),
    ]

    student_ids = []
    student_group_map = []

    for fn, ln, email, phone, dob, gender, balance, gidx in students_raw:
        existing_s = await conn.fetchrow(
            f"SELECT s.id FROM {schema}.students s JOIN {schema}.users u ON u.id=s.user_id WHERE u.email=$1",
            email
        )
        if existing_s:
            student_ids.append(str(existing_s["id"]))
            student_group_map.append((str(existing_s["id"]), gidx))
        else:
            u_row = await conn.fetchrow(
                f"""INSERT INTO {schema}.users (first_name,last_name,email,password_hash,role,phone,is_active,is_verified)
                    VALUES ($1,$2,$3,$4,'student',$5,TRUE,TRUE) RETURNING id""",
                fn, ln, email, hash_password("Student123!"), phone
            )
            s_row = await conn.fetchrow(
                f"""INSERT INTO {schema}.students (user_id,branch_id,date_of_birth,gender,balance,is_active)
                    VALUES ($1,$2,$3,$4,$5,TRUE) RETURNING id""",
                str(u_row["id"]), branch_id, dob, gender, balance
            )
            sid = str(s_row["id"])
            student_ids.append(sid)
            student_group_map.append((sid, gidx))

            # Gamification profile
            await conn.execute(
                f"""INSERT INTO {schema}.gamification_profiles (student_id, total_xp, current_level, weekly_xp)
                    VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING""",
                sid, 0, 1, 0
            )

    # Assign students to groups
    for sid, gidx in student_group_map:
        if gidx < len(group_ids):
            await conn.execute(
                f"""INSERT INTO {schema}.student_groups (student_id, group_id, joined_at)
                    VALUES ($1, $2, $3) ON CONFLICT DO NOTHING""",
                sid, group_ids[gidx], date(2026, 1, 15)
            )

    print(f"   ✅  {len(students_raw)} ta o'quvchi, guruhlarga biriktirildi")

    # ── Attendance (last 7 days) ───────────────────────────────────
    att_count = 0
    for i in range(7):
        att_date = date.today() - timedelta(days=i)
        if att_date.weekday() >= 5:  # skip weekend
            continue
        for j, (sid, gidx) in enumerate(student_group_map[:8]):
            if gidx >= len(group_ids):
                continue
            status = "absent" if (i == 2 and j % 3 == 0) else "late" if (j % 5 == 0) else "present"
            try:
                await conn.execute(
                    f"""INSERT INTO {schema}.attendance
                        (student_id, group_id, teacher_id, date, status)
                        VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING""",
                    sid, group_ids[gidx],
                    teacher_ids[gidx % len(teacher_ids)],
                    att_date, status
                )
                att_count += 1
            except Exception:
                pass

    print(f"   ✅  Davomat yozuvlari: {att_count} ta (so'nggi 7 kun)")

    # ── Payments ──────────────────────────────────────────────────
    pay_count = 0
    for j, (sid, gidx) in enumerate(student_group_map):
        if gidx >= len(group_ids):
            continue
        amount = groups_data[gidx][4]  # monthly_fee
        method = "click" if j % 2 == 0 else "cash"
        status = "completed" if j != 4 else "pending" 
        try:
            await conn.execute(
                f"""INSERT INTO {schema}.payments
                    (student_id, group_id, amount, payment_method, status,
                     period_month, period_year, paid_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8) """,
                sid, group_ids[gidx], amount, method, status,
                3, 2026,
                datetime.now() - timedelta(days=j)
            )
            pay_count += 1
        except Exception:
            pass

    print(f"   ✅  To'lovlar: {pay_count} ta (mart 2026)")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  ✅  SEED MUVAFFAQIYATLI TUGADI!")
    print("=" * 55)
    print("""
  📊  Yaratilgan ma'lumotlar:
  ┌─────────────────────────────────────────────┐
  │  Super Admin kirish:                        │
  │    Tenant  : platform                       │
  │    Email   : superadmin@edusaas.uz          │
  │    Parol   : Admin123!                      │
  ├─────────────────────────────────────────────┤
  │  Demo markaz admin kirish:                  │
  │    Tenant  : demo-markaz                    │
  │    Email   : admin@demo-markaz.uz           │
  │    Parol   : Admin123!                      │
  ├─────────────────────────────────────────────┤
  │  O'qituvchi (barcha):                       │
  │    Parol   : Teacher123!                    │
  ├─────────────────────────────────────────────┤
  │  O'quvchi (barcha):                         │
  │    Parol   : Student123!                    │
  └─────────────────────────────────────────────┘

  🚀  Login URL: http://localhost:3000/uz/login
    """)


if __name__ == "__main__":
    asyncio.run(seed())