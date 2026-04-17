"""
Bu skript gamification jadvallarini barcha tenant schemalarida yaratadi.
Ishlatish: python create_gamification_tables.py
"""
import asyncio
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# DATABASE_URL dan asyncpg formatiga o'tkazish
DB_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://edusaas:edusaas_pass@localhost:5432/edusaas")
# postgresql+asyncpg:// → postgresql://
PG_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql://")


async def main():
    conn = await asyncpg.connect(PG_URL)
    print(f"✅ DB ga ulandi")

    # Barcha tenant schemalarini olish
    tenants = await conn.fetch(
        "SELECT schema_name, slug FROM public.tenants WHERE is_active = true"
    )
    print(f"📋 {len(tenants)} ta tenant topildi")

    for tenant in tenants:
        schema = tenant["schema_name"]
        slug   = tenant["slug"]
        print(f"\n🔧 Schema: {schema} ({slug})")

        # gamification_profiles
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".gamification_profiles (
                id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id         UUID UNIQUE NOT NULL REFERENCES "{schema}".students(id),
                total_xp           INTEGER DEFAULT 0,
                current_level      INTEGER DEFAULT 1,
                current_streak     INTEGER DEFAULT 0,
                max_streak         INTEGER DEFAULT 0,
                last_activity_date DATE,
                weekly_xp          INTEGER DEFAULT 0,
                weekly_reset_at    TIMESTAMPTZ,
                created_at         TIMESTAMPTZ DEFAULT NOW(),
                updated_at         TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print(f"  ✅ gamification_profiles")

        # xp_transactions
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".xp_transactions (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id   UUID NOT NULL REFERENCES "{schema}".students(id),
                amount       INTEGER NOT NULL,
                reason       VARCHAR(100),
                reference_id UUID,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print(f"  ✅ xp_transactions")

        # achievements
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".achievements (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug            VARCHAR(50) NOT NULL UNIQUE,
                name_uz         VARCHAR(100) NOT NULL,
                name_ru         VARCHAR(100),
                description_uz  TEXT,
                icon            VARCHAR(10),
                xp_reward       INTEGER DEFAULT 0,
                condition_type  VARCHAR(50) NOT NULL,
                condition_value INTEGER NOT NULL,
                is_active       BOOLEAN DEFAULT TRUE
            )
        """)
        print(f"  ✅ achievements")

        # student_achievements
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".student_achievements (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id     UUID NOT NULL REFERENCES "{schema}".students(id),
                achievement_id UUID NOT NULL REFERENCES "{schema}".achievements(id),
                earned_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(student_id, achievement_id)
            )
        """)
        print(f"  ✅ student_achievements")

        # notifications
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".notifications (
                id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id    UUID NOT NULL REFERENCES "{schema}".users(id),
                type       VARCHAR(50) NOT NULL,
                title      VARCHAR(200) NOT NULL,
                body       TEXT NOT NULL,
                data       JSONB DEFAULT '{{}}',
                channel    VARCHAR(20) DEFAULT 'telegram',
                is_read    BOOLEAN DEFAULT FALSE,
                sent_at    TIMESTAMPTZ,
                read_at    TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print(f"  ✅ notifications")

        # Default achievements
        await conn.execute(f"""
            INSERT INTO "{schema}".achievements
                (slug, name_uz, name_ru, icon, xp_reward, condition_type, condition_value)
            VALUES
                ('streak_7',     '7 kunlik streak',    '7-дневный стрик',   '🔥', 100, 'streak', 7),
                ('streak_30',    '30 kunlik streak',   '30-дневный стрик',  '💎', 500, 'streak', 30),
                ('xp_100',       '100 XP',             '100 XP',            '⭐',   0, 'xp',     100),
                ('xp_1000',      '1000 XP',            '1000 XP',           '🏆',  50, 'xp',     1000),
                ('xp_5000',      '5000 XP',            '5000 XP',           '👑', 200, 'xp',     5000),
                ('first_lesson', 'Birinchi dars',      'Первый урок',       '📚',  20, 'xp',     20)
            ON CONFLICT (slug) DO NOTHING
        """)
        print(f"  ✅ default achievements qo'shildi")

        # Indekslar
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_xp_student_{schema.replace('-','_')}
            ON "{schema}".xp_transactions(student_id)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_notif_user_{schema.replace('-','_')}
            ON "{schema}".notifications(user_id)
        """)
        print(f"  ✅ indekslar")

    await conn.close()
    print(f"\n🎉 Barcha jadvallar yaratildi!")

    # Alembic stamp
    print("\n💡 Endi quyidagini ishlatish kerak:")
    print("   alembic stamp 002_gamification")


if __name__ == "__main__":
    asyncio.run(main())