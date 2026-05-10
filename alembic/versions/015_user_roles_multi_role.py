"""015_user_roles_multi_role

Bitta foydalanuvchi bir nechta rolda bo'lishi uchun `user_roles` jadvali.
Eski `users.role` saqlanadi (default/active rol), yangi jadval — user'ning
egalik qiladigan barcha rollari ro'yxati.

Multi-tenant: barcha tenant schema'larda yaratiladi va `users` dan backfill qilinadi.
"""
from alembic import op
import sqlalchemy as sa


revision = '015_user_roles_multi_role'
down_revision = '014_notification_system_v2'
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
        # users jadvali mavjudligini tekshiramiz (bo'sh tenant'lar uchun xavfsiz skip)
        exists = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :s AND table_name = 'users'"
        ), {"s": schema}).scalar()
        if not exists:
            continue

        conn.execute(sa.text(f'SET search_path TO "{schema}", public'))

        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role       VARCHAR(20) NOT NULL,
                branch_id  UUID NULL REFERENCES branches(id) ON DELETE SET NULL,
                is_active  BOOLEAN NOT NULL DEFAULT TRUE,
                granted_by UUID NULL,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, role)
            )
        """))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS idx_user_roles_user_active "
            "ON user_roles(user_id, is_active)"
        ))

        # Backfill: mavjud users.role → user_roles
        conn.execute(sa.text("""
            INSERT INTO user_roles (user_id, role, branch_id, is_active)
            SELECT id, role, branch_id, is_active
            FROM users
            WHERE role IS NOT NULL
            ON CONFLICT (user_id, role) DO NOTHING
        """))

    # search_path ni qayta tiklash
    conn.execute(sa.text('SET search_path TO public'))


def downgrade():
    conn = op.get_bind()
    schemas = get_tenant_schemas(conn)
    for schema in schemas:
        conn.execute(sa.text(f'SET search_path TO "{schema}", public'))
        conn.execute(sa.text("DROP TABLE IF EXISTS user_roles"))
    conn.execute(sa.text('SET search_path TO public'))
