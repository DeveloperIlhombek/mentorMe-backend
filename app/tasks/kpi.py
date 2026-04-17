"""app/tasks/kpi.py — KPI Celery tasklari."""
from datetime import date
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(name="tasks.calculate_kpi_daily")
def calculate_kpi_daily():
    """
    Har kuni ishga tushadi.
    Bugun kpi_calc_day == today.day bo'lgan o'qituvchilar uchun
    o'tgan oy KPI ni hisoblaydi.
    Misol: o'qituvchining kpi_calc_day=15 bo'lsa,
           har oyning 15-kuni o'tgan oy hisoblash ishga tushadi.
    """
    import asyncio
    from app.core.database import get_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select, text
    from app.models.tenant.teacher import Teacher
    from app.models.public.tenant import Tenant

    async def _run():
        today = date.today()
        engine = get_engine()

        async with AsyncSession(engine) as db:
            tenants = (await db.execute(
                select(Tenant).where(Tenant.is_active == True)
            )).scalars().all()

        for tenant in tenants:
            schema = tenant.schema_name
            try:
                await _process_tenant(schema, today)
            except Exception as e:
                logger.error(f"Tenant {schema} KPI xatosi: {e}")

    asyncio.run(_run())


async def _process_tenant(schema: str, today: date):
    """Bir tenant uchun: bugun hisoblash kuni bo'lgan o'qituvchilarni topib KPI hisoblash."""
    from app.core.database import get_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select, text
    from app.models.tenant.teacher import Teacher
    from app.services import kpi as kpi_svc

    engine = get_engine()

    async with AsyncSession(engine) as db:
        # Schema ni o'rnatish
        await db.execute(text(f'SET search_path TO "{schema}", public'))

        # Bugun kpi_calc_day == today.day bo'lgan faol o'qituvchilar
        teachers = (await db.execute(
            select(Teacher).where(
                Teacher.is_active    == True,
                Teacher.kpi_calc_day == today.day,
            )
        )).scalars().all()

        if not teachers:
            return

        # O'tgan oy (hisoblash sanasi joriy oy uchun o'tgan oyni hisoblaydii)
        if today.month == 1:
            calc_month = 12
            calc_year  = today.year - 1
        else:
            calc_month = today.month - 1
            calc_year  = today.year

        logger.info(
            f"[{schema}] {len(teachers)} ta o'qituvchi uchun "
            f"{calc_month}/{calc_year} KPI hisoblanyapti"
        )

        for teacher in teachers:
            try:
                result = await kpi_svc.calculate_for_teacher(
                    db, teacher.id, calc_month, calc_year
                )
                logger.info(
                    f"  → {teacher.id}: net={result['net_salary']:,.0f} so'm"
                )
            except Exception as e:
                logger.error(f"  ✗ {teacher.id}: {e}")


@shared_task(name="tasks.calculate_churn_risks_daily")
def calculate_churn_risks_daily():
    """Har kuni 02:00 — barcha tenantlar uchun churn risk hisoblash."""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select, text
    from app.core.database import get_engine
    from app.models.public.tenant import Tenant

    async def _run():
        engine = get_engine()
        async with AsyncSession(engine) as db:
            tenants = (await db.execute(
                select(Tenant).where(Tenant.is_active == True)
            )).scalars().all()

        for tenant in tenants:
            try:
                async with AsyncSession(engine) as db:
                    await db.execute(
                        text(f'SET search_path TO "{tenant.schema_name}", public')
                    )
                    from app.services.marketing import calculate_churn_risks
                    count = await calculate_churn_risks(db)
                    get_task_logger(__name__).info(
                        f"[{tenant.schema_name}] churn: {count} ta yangilandi"
                    )
            except Exception as e:
                get_task_logger(__name__).error(f"Churn xatosi {tenant.schema_name}: {e}")

    asyncio.run(_run())
