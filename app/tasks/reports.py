import structlog
from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="app.tasks.reports.generate_monthly_report")
def generate_monthly_report():
    """Auto-generate monthly financial + attendance reports on 1st of month."""
    logger.info("task_generate_monthly_report_started")
    # TODO: For each active tenant, generate PDF+Excel report, upload to S3, notify admin
    pass


@celery_app.task(name="app.tasks.reports.generate_report_for_tenant")
def generate_report_for_tenant(tenant_slug: str, report_type: str, month: int, year: int):
    """Generate a specific report for a tenant."""
    logger.info("generate_report", tenant=tenant_slug, type=report_type, month=month, year=year)
    # TODO: Use reportlab/openpyxl to generate, upload to S3, return download URL
    pass
