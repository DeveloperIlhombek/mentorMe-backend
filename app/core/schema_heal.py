"""
app/core/schema_heal.py

Tenant schemalardagi yetishmayotgan ustunlarni avtomatik tuzatish.
Migration ishlatilmaganda 500 xatosini oldini olish uchun.

Faqat IDempotent ALTER TABLE / CREATE TABLE IF NOT EXISTS so'rovlari
ishlatiladi — mavjud ma'lumotlarga ta'sir qilmaydi.

Qo'llaniladigan SQL ro'yxati `tenant_provisioning._ALTER_STATEMENTS` dan
olinadi — shu tariqa har bir migration shu yerga yangilanmasdan ham
mavjud tenantlar avtomatik tuzaladi.
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)


async def heal_tenant_schemas(engine: AsyncEngine) -> None:
    """Barcha tenant_* schemalarda yetishmayotgan ustunlarni qo'shadi."""
    try:
        from app.services.tenant_provisioning import _ALTER_STATEMENTS
    except Exception as exc:
        log.warning("schema_heal: cannot import _ALTER_STATEMENTS: %s", exc)
        return

    try:
        async with engine.connect() as conn:
            schemas = (
                await conn.execute(text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'tenant_%'"
                ))
            ).scalars().all()

            if not schemas:
                return

            for schema in schemas:
                schema_safe = schema.replace("-", "_")
                applied = 0
                for stmt_template in _ALTER_STATEMENTS:
                    sql = stmt_template.format(schema=schema, schema_safe=schema_safe)
                    try:
                        # Har bir statement o'z savepoint ida — birortasi xato
                        # bersa ham qolganlari bajariladi.
                        async with conn.begin_nested():
                            await conn.execute(text(sql))
                        applied += 1
                    except Exception as exc:
                        log.debug(
                            "schema_heal: skip in %s: %s -> %s",
                            schema, sql[:100], exc,
                        )
                log.debug("schema_heal: %s — %d patch tatbiq etildi", schema, applied)
            await conn.commit()
            log.info("✅ schema_heal: %d tenant schema tekshirildi", len(schemas))
    except Exception as exc:
        log.warning("schema_heal failed: %s", exc)
