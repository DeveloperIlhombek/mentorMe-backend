"""
app/api/v1/router.py
Barcha v1 routerlarini birlashtiradi.
"""
from fastapi import APIRouter

from app.api.v1.admin.attendance import router as attendance_router
from app.api.v1.admin.branches import router as branches_router
from app.api.v1.admin.finance import router as finance_router
from app.api.v1.admin.groups import router as groups_router
from app.api.v1.admin.kpi import router as kpi_router
from app.api.v1.admin.marketing import router as marketing_router
from app.api.v1.admin.payments import router as payments_router
from app.api.v1.admin.reports import router as reports_router

# Admin
from app.api.v1.admin.inspectors import router as inspectors_router
from app.api.v1.admin.invites import router as invites_router
from app.api.v1.admin.students import router as students_router
from app.api.v1.admin.teachers import router as teachers_router
from app.api.v1.admin.trash import router as trash_router
from app.api.v1.admin.progress import router as progress_router
from app.api.v1.admin.lesson_cancellations import router as lesson_cancellations_router
from app.api.v1.admin.assessment import router as admin_assessment_router
from app.api.v1.gamification import router as gamification_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.parent import router as parent_router
from app.api.v1.student_routes import router as student_router
from app.api.v1.teacher_progress import router as teacher_progress_router

# Boshqa rollar
from app.api.v1.superadmin import router as superadmin_router
from app.api.v1.teacher import router as teacher_router
from app.api.v1.teacher_syllabus import router as teacher_syllabus_router

api_router = APIRouter()

# Admin
api_router.include_router(students_router)
api_router.include_router(groups_router)
api_router.include_router(attendance_router)
api_router.include_router(payments_router)
api_router.include_router(teachers_router)
api_router.include_router(inspectors_router)
api_router.include_router(reports_router)
api_router.include_router(finance_router)
api_router.include_router(branches_router)
api_router.include_router(kpi_router)
api_router.include_router(marketing_router)
api_router.include_router(trash_router)
api_router.include_router(invites_router)
api_router.include_router(progress_router)
api_router.include_router(lesson_cancellations_router)
api_router.include_router(admin_assessment_router)

# Rollar
api_router.include_router(superadmin_router)
api_router.include_router(teacher_router)
api_router.include_router(teacher_syllabus_router)
api_router.include_router(teacher_progress_router)
api_router.include_router(student_router)
api_router.include_router(parent_router)
api_router.include_router(gamification_router)
api_router.include_router(notifications_router)