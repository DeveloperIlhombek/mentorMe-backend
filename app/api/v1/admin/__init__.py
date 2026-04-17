"""
app/api/v1/admin/__init__.py

Admin routerlarini birlashtiradi.
Har bir modul o'z router.prefix bilan keladi:
  /students, /groups, /attendance, /payments
"""
from fastapi import APIRouter

from app.api.v1.admin.students   import router as students_router
from app.api.v1.admin.groups     import router as groups_router
from app.api.v1.admin.attendance import router as attendance_router
from app.api.v1.admin.payments   import router as payments_router

# Barcha admin routerlarini bitta router ostida birlashtirish
router = APIRouter()
router.include_router(students_router)
router.include_router(groups_router)
router.include_router(attendance_router)
router.include_router(payments_router)
