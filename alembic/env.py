"""
alembic/env.py

Multi-tenant migration strategiyasi:
  - public schema: tenants, subscription_plans
  - tenant_{slug} schema: har bir markaz uchun alohida

Ishlatish:
  # Yangi migration yaratish:
  alembic revision --autogenerate -m "add users table"

  # Barcha migrationlarni ishlatish:
  alembic upgrade head

  # Bitta versiyaga qaytish:
  alembic downgrade -1
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Alembic Config object
config = context.config

# Logging sozlash
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Barcha modellarni import qilish — autogenerate uchun kerak
from app.core.database import Base
from app.core.config import settings

# .env dan DATABASE_URL olish (alembic.ini dan ustun)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Barcha modellar import qilinishi kerak
from app.models.public.tenant import Tenant, SubscriptionPlan
from app.models.tenant.user        import User
from app.models.tenant.branch      import Branch
from app.models.tenant.teacher     import Teacher
from app.models.tenant.group       import Group
from app.models.tenant.student     import Student, StudentGroup
from app.models.tenant.attendance  import Attendance
from app.models.tenant.payment     import Payment
from app.models.tenant.gamification import (
    GamificationProfile, XpTransaction, Achievement, StudentAchievement
)
from app.models.tenant.notification import Notification

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Offline mode — DB ulanishisiz SQL skript chiqaradi."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Online mode — async engine bilan."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
