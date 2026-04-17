"""007_syllabus_notifications

Yangi jadvallar:
  - syllabuses         : O'quv yo'li (kurs syllabus)
  - syllabus_topics    : Mavzular (ketma-ket)
  - syllabus_assignments: Guruh yoki o'quvchiga biriktirish
  - syllabus_progress  : O'quvchi progress (qaysi mavzu bajarildi)
  - teacher_requests   : O'qituvchi so'rovlari (yangi tur: assign_to_group)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = '007_syllabus_notifications'
down_revision = '006_branches'
branch_labels = None
depends_on = None


def get_tenant_schemas(conn):
    result = conn.execute(sa.text(
        "SELECT schema_name FROM public.tenants WHERE is_active = true"
    ))
    return [row[0] for row in result]


def upgrade():
    conn = op.get_bind()
    schemas = get_tenant_schemas(conn)

    for schema in schemas:
        conn.execute(sa.text(f'SET search_path TO "{schema}", public'))

        # ── syllabuses ──────────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".syllabuses (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title        VARCHAR(200) NOT NULL,
                description  TEXT,
                subject      VARCHAR(100),
                created_by   UUID REFERENCES "{schema}".users(id),
                status       VARCHAR(20) DEFAULT 'active',
                xp_per_topic INTEGER DEFAULT 50,
                color        VARCHAR(7)  DEFAULT '#4f8ef7',
                icon         VARCHAR(10) DEFAULT '📚',
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                updated_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        # ── syllabus_topics ─────────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".syllabus_topics (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                syllabus_id  UUID NOT NULL REFERENCES "{schema}".syllabuses(id) ON DELETE CASCADE,
                title        VARCHAR(200) NOT NULL,
                description  TEXT,
                order_index  INTEGER NOT NULL DEFAULT 0,
                xp_reward    INTEGER DEFAULT 50,
                is_active    BOOLEAN DEFAULT TRUE,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_topics_syllabus_{schema.replace('-','_')}
            ON "{schema}".syllabus_topics(syllabus_id, order_index)
        """))

        # ── syllabus_assignments ────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".syllabus_assignments (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                syllabus_id  UUID NOT NULL REFERENCES "{schema}".syllabuses(id) ON DELETE CASCADE,
                target_type  VARCHAR(20) NOT NULL CHECK (target_type IN ('group','student')),
                target_id    UUID NOT NULL,
                assigned_by  UUID REFERENCES "{schema}".users(id),
                assigned_at  TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(syllabus_id, target_type, target_id)
            )
        """))

        # ── syllabus_progress ───────────────────────────────────────────
        conn.execute(sa.text(f"""
            CREATE TABLE IF NOT EXISTS "{schema}".syllabus_progress (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                student_id    UUID NOT NULL REFERENCES "{schema}".students(id) ON DELETE CASCADE,
                topic_id      UUID NOT NULL REFERENCES "{schema}".syllabus_topics(id) ON DELETE CASCADE,
                completed_at  TIMESTAMPTZ DEFAULT NOW(),
                completed_by  UUID REFERENCES "{schema}".users(id),
                xp_given      INTEGER DEFAULT 0,
                UNIQUE(student_id, topic_id)
            )
        """))

        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_progress_student_{schema.replace('-','_')}
            ON "{schema}".syllabus_progress(student_id)
        """))

        conn.execute(sa.text(f"""
            CREATE INDEX IF NOT EXISTS idx_progress_topic_{schema.replace('-','_')}
            ON "{schema}".syllabus_progress(topic_id)
        """))

        # ── teacher_requests (yangi turlar qo'shiladi) ──────────────────
        # Mavjud jadval bor, lekin assign_to_group turi yo'q —
        # constraint yo'q bo'lsa, yozuv kiritganda xato beradi.
        # ALTER TYPE qo'shamiz (agar VARCHAR bo'lsa, cheklov yo'q).
        # notes ustunini qo'shamiz (agar yo'q bo'lsa)
        try:
            conn.execute(sa.text(f"""
                ALTER TABLE "{schema}".inspector_requests
                ADD COLUMN IF NOT EXISTS extra_data JSONB DEFAULT '{{}}'::jsonb
            """))
        except Exception:
            pass

        print(f"✅ {schema}: syllabus jadvallar yaratildi")

    conn.execute(sa.text("SET search_path TO public"))


def downgrade():
    conn = op.get_bind()
    schemas = get_tenant_schemas(conn)
    for schema in schemas:
        conn.execute(sa.text(f'SET search_path TO "{schema}", public'))
        for tbl in ['syllabus_progress', 'syllabus_assignments',
                    'syllabus_topics', 'syllabuses']:
            conn.execute(sa.text(f'DROP TABLE IF EXISTS "{schema}".{tbl} CASCADE'))
    conn.execute(sa.text("SET search_path TO public"))
