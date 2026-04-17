"""
app/schemas/__init__.py
Barcha schemalarni shu yerdan import qilish mumkin.

Ishlatish:
    from app.schemas import StudentCreate, GroupOut, PaymentCreate
"""
from app.schemas.student     import StudentCreate, StudentUpdate, StudentOut, StudentShort
from app.schemas.group       import GroupCreate, GroupUpdate, GroupOut, ScheduleItem
from app.schemas.attendance  import AttendanceBulkCreate, AttendanceItem, AttendanceOut, AttendanceSummary
from app.schemas.payment     import PaymentCreate, PaymentOut
from app.schemas.gamification import GamificationOut, LeaderboardEntry
from app.schemas.auth        import (
    TelegramAuthRequest, WebLoginRequest, WebRegisterRequest,
    TokenResponse, RefreshRequest,
)

__all__ = [
    "StudentCreate", "StudentUpdate", "StudentOut", "StudentShort",
    "GroupCreate", "GroupUpdate", "GroupOut", "ScheduleItem",
    "AttendanceBulkCreate", "AttendanceItem", "AttendanceOut", "AttendanceSummary",
    "PaymentCreate", "PaymentOut",
    "GamificationOut", "LeaderboardEntry",
    "TelegramAuthRequest", "WebLoginRequest", "WebRegisterRequest",
    "TokenResponse", "RefreshRequest",
]


def ok(data, meta: dict | None = None) -> dict:
    """Standart muvaffaqiyatli response formati."""
    result = {"success": True, "data": data}
    if meta:
        result["meta"] = meta
    return result


def err(code: str, message: str) -> dict:
    """Standart xato response formati."""
    return {"success": False, "error": {"code": code, "message": message}}
