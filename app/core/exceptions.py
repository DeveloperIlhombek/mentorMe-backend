from fastapi import HTTPException


class EduSaaSException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


class AuthInvalidInitData(EduSaaSException):
    def __init__(self):
        super().__init__(401, "AUTH_INVALID_INIT_DATA", "Telegram initData yaroqsiz")

class AuthTokenExpired(EduSaaSException):
    def __init__(self):
        super().__init__(401, "AUTH_TOKEN_EXPIRED", "Token muddati tugagan")

class AuthInsufficientRole(EduSaaSException):
    def __init__(self):
        super().__init__(403, "AUTH_INSUFFICIENT_ROLE", "Ruxsat yo'q")

class TenantNotFound(EduSaaSException):
    def __init__(self):
        super().__init__(404, "TENANT_NOT_FOUND", "Ta'lim markaz topilmadi")

class TenantSuspended(EduSaaSException):
    def __init__(self):
        super().__init__(403, "TENANT_SUSPENDED", "Ta'lim markaz to'xtatilgan")

class TenantLimitExceeded(EduSaaSException):
    def __init__(self, resource: str = ""):
        super().__init__(402, "TENANT_LIMIT_EXCEEDED", f"Tarif limiti oshdi: {resource}")

class StudentNotFound(EduSaaSException):
    def __init__(self):
        super().__init__(404, "STUDENT_NOT_FOUND", "O'quvchi topilmadi")

class GroupNotFound(EduSaaSException):
    def __init__(self):
        super().__init__(404, "GROUP_NOT_FOUND", "Guruh topilmadi")

class GroupFull(EduSaaSException):
    def __init__(self):
        super().__init__(409, "GROUP_FULL", "Guruh to'lgan (max_students)")

class ScheduleConflict(EduSaaSException):
    def __init__(self):
        super().__init__(409, "SCHEDULE_CONFLICT", "Jadval ziddiyati (xona band)")

class PaymentAlreadyExists(EduSaaSException):
    def __init__(self):
        super().__init__(409, "PAYMENT_ALREADY_EXISTS", "Bu oy uchun to'lov allaqachon mavjud")

class ClickSignatureInvalid(EduSaaSException):
    def __init__(self):
        super().__init__(400, "CLICK_SIGNATURE_INVALID", "Click imzo xatosi")

class AssessmentNotAvailable(EduSaaSException):
    def __init__(self):
        super().__init__(404, "ASSESSMENT_NOT_AVAILABLE", "Test hozir mavjud emas")

class MaxAttemptsReached(EduSaaSException):
    def __init__(self):
        super().__init__(429, "MAX_ATTEMPTS_REACHED", "Maksimal urinishlar tugadi")
