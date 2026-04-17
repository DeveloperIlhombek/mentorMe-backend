"""
006_branches migration xatosini tuzatish.
Muammo: ck_user_role constraint super_admin ni o'z ichiga olmagan.

Ishlatish:
    python fix_006_migration.py
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

        # 1. users.branch_id — agar yo'q bo'lsa qo'shish
        try:
            await conn.execute(f"""
                ALTER TABLE "{s}".users
                ADD COLUMN IF NOT EXISTS branch_id UUID
                    REFERENCES "{s}".branches(id) ON DELETE SET NULL
            """)
            print("  ✅ users.branch_id")
        except Exception as e:
            print(f"  ⚠️  users.branch_id: {e}")

        # 2. Eski noto'g'ri constraint ni olib tashlash (agar qo'shilgan bo'lsa)
        try:
            await conn.execute(f"""
                ALTER TABLE "{s}".users
                DROP CONSTRAINT IF EXISTS ck_user_role
            """)
            print("  ✅ old ck_user_role dropped")
        except Exception as e:
            print(f"  ⚠️  drop constraint: {e}")

        # 3. To'g'ri constraint qo'shish (super_admin ham bor)
        try:
            await conn.execute(f"""
                ALTER TABLE "{s}".users
                ADD CONSTRAINT ck_user_role
                CHECK (role IN (
                    'super_admin','admin','teacher',
                    'student','parent','inspector'
                ))
            """)
            print("  ✅ ck_user_role (to'g'ri versiya)")
        except Exception as e:
            print(f"  ⚠️  add constraint: {e}")

        # 4. branches.manager_id — agar yo'q bo'lsa qo'shish
        try:
            await conn.execute(f"""
                ALTER TABLE "{s}".branches
                ADD COLUMN IF NOT EXISTS manager_id UUID
                    REFERENCES "{s}".users(id) ON DELETE SET NULL
            """)
            print("  ✅ branches.manager_id")
        except Exception as e:
            print(f"  ⚠️  branches.manager_id: {e}")

        # 5. branch_expenses jadvali
        try:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS "{s}".branch_expenses (
                    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    branch_id        UUID NOT NULL
                                         REFERENCES "{s}".branches(id) ON DELETE CASCADE,
                    requested_by     UUID
                                         REFERENCES "{s}".users(id) ON DELETE SET NULL,
                    approved_by      UUID
                                         REFERENCES "{s}".users(id) ON DELETE SET NULL,
                    title            VARCHAR(300) NOT NULL,
                    description      TEXT,
                    amount           DECIMAL(15,2) NOT NULL,
                    category         VARCHAR(100),
                    status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                                         CHECK (status IN
                                           ('pending','approved','rejected','paid')),
                    rejected_reason  TEXT,
                    approved_at      TIMESTAMPTZ,
                    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            print("  ✅ branch_expenses")
        except Exception as e:
            print(f"  ⚠️  branch_expenses: {e}")

        # 6. inspector_requests jadvali
        try:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS "{s}".inspector_requests (
                    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    branch_id           UUID NOT NULL
                                            REFERENCES "{s}".branches(id) ON DELETE CASCADE,
                    inspector_id        UUID
                                            REFERENCES "{s}".users(id) ON DELETE SET NULL,
                    request_type        VARCHAR(30) NOT NULL DEFAULT 'add_teacher'
                                            CHECK (request_type IN ('add_teacher','other')),
                    first_name          VARCHAR(100) NOT NULL,
                    last_name           VARCHAR(100),
                    phone               VARCHAR(20),
                    subjects            VARCHAR(500),
                    salary_type         VARCHAR(20),
                    salary_amount       DECIMAL(12,2),
                    notes               TEXT,
                    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                                            CHECK (status IN
                                              ('pending','approved','rejected')),
                    reviewed_by         UUID
                                            REFERENCES "{s}".users(id) ON DELETE SET NULL,
                    reject_reason       TEXT,
                    reviewed_at         TIMESTAMPTZ,
                    created_teacher_id  UUID
                                            REFERENCES "{s}".teachers(id) ON DELETE SET NULL,
                    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            print("  ✅ inspector_requests")
        except Exception as e:
            print(f"  ⚠️  inspector_requests: {e}")

        # 7. Indekslar
        tag = s[-8:].replace("-", "_")
        for idx_sql in [
            f'CREATE INDEX IF NOT EXISTS idx_users_branch_{tag} ON "{s}".users (branch_id) WHERE branch_id IS NOT NULL',
            f'CREATE INDEX IF NOT EXISTS idx_expenses_branch_{tag} ON "{s}".branch_expenses (branch_id, status)',
            f'CREATE INDEX IF NOT EXISTS idx_insp_req_branch_{tag} ON "{s}".inspector_requests (branch_id, status)',
        ]:
            try:
                await conn.execute(idx_sql)
            except Exception:
                pass
        print("  ✅ indexes")

    # Alembic version ni yangilash
    try:
        await conn.execute("""
            UPDATE alembic_version SET version_num = '006_branches'
            WHERE version_num = '005_kpi_marketing'
        """)
        result = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"\n✅ alembic_version: {result}")
    except Exception as e:
        print(f"\n⚠️  alembic version update: {e}")

    await conn.close()
    print("\n🎉 Migration tuzatildi! Endi uvicorn ishlatishingiz mumkin.")


if __name__ == "__main__":
    asyncio.run(main())
