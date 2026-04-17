"""
app/services/report.py

Hisobotlar:
  - Moliyaviy hisobot (oylik daromad, qarzlar)
  - Davomat hisoboti (guruh/o'quvchi bo'yicha)
  - O'qituvchi ish haqi
  - Qarzdorlar ro'yxati

Format: Excel (openpyxl) — PDF keyinchalik qo'shiladi.
Async generatsiya: Celery task orqali fon rejimida.
"""
import io
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession


# ─── Excel yordamchi ─────────────────────────────────────────────────

def _new_workbook(title: str):
    """Yangi Excel workbook yaratish."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        raise ImportError("openpyxl o'rnatilmagan: pip install openpyxl")

    wb = Workbook()
    ws = wb.active
    ws.title = title

    # Stil konstantlari
    HEADER_FILL  = PatternFill("solid", fgColor="1E40AF")
    HEADER_FONT  = Font(color="FFFFFF", bold=True, size=11)
    BORDER_SIDE  = Side(style="thin", color="D1D5DB")
    CELL_BORDER  = Border(
        left=BORDER_SIDE, right=BORDER_SIDE,
        top=BORDER_SIDE,  bottom=BORDER_SIDE,
    )
    CENTER = Alignment(horizontal="center", vertical="center")

    return wb, ws, {
        "header_fill": HEADER_FILL,
        "header_font": HEADER_FONT,
        "border":      CELL_BORDER,
        "center":      CENTER,
    }


def _set_headers(ws, styles: dict, headers: list, row: int = 1):
    """Jadval sarlavhalarini qo'yish."""
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.fill      = styles["header_fill"]
        cell.font      = styles["header_font"]
        cell.border    = styles["border"]
        cell.alignment = styles["center"]
        ws.column_dimensions[cell.column_letter].width = max(len(str(header)) + 4, 12)


def _set_row(ws, styles: dict, values: list, row: int):
    """Ma'lumot qatorini qo'yish."""
    for col, value in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=value)
        cell.border    = styles["border"]
        cell.alignment = styles["center"]


def _to_bytes(wb) -> bytes:
    """Workbook ni bytes ga aylantirish."""
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─── 1. Moliyaviy hisobot ─────────────────────────────────────────────

async def financial_report(
    db: AsyncSession,
    month: int,
    year: int,
) -> bytes:
    """
    Oylik moliyaviy hisobot Excel.
    Ustunlar: O'quvchi, Guruh, To'lov summasi, Usuli, Sana, Holat
    """
    from app.models.tenant import Payment, Student, User, Group

    stmt = (
        select(Payment, Student, User, Group)
        .join(Student, Payment.student_id == Student.id)
        .join(User,    Student.user_id    == User.id)
        .outerjoin(Group, Payment.group_id == Group.id)
        .where(
            and_(
                extract("month", Payment.created_at) == month,
                extract("year",  Payment.created_at) == year,
            )
        )
        .order_by(Payment.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    wb, ws, styles = _new_workbook(f"Moliyaviy hisobot {month}-{year}")

    # Title
    ws.merge_cells("A1:G1")
    title_cell = ws["A1"]
    title_cell.value = f"Moliyaviy hisobot — {month}/{year}"
    from openpyxl.styles import Font
    title_cell.font  = Font(bold=True, size=14)

    MONTH_NAMES = ["", "Yanvar","Fevral","Mart","Aprel","May","Iyun",
                   "Iyul","Avgust","Sentabr","Oktabr","Noyabr","Dekabr"]

    headers = ["#", "O'quvchi", "Guruh", "Summa (so'm)", "Usul", "Sana", "Holat"]
    _set_headers(ws, styles, headers, row=3)

    total_sum = 0
    for i, (pay, st, u, g) in enumerate(rows, start=1):
        _set_row(ws, styles, [
            i,
            f"{u.first_name} {u.last_name or ''}".strip(),
            g.name if g else "—",
            float(pay.amount),
            "Click" if pay.payment_method == "click" else "Naqd",
            pay.paid_at.strftime("%d.%m.%Y") if pay.paid_at else "—",
            "Tasdiqlandi" if pay.status == "completed" else pay.status,
        ], row=i + 3)
        if pay.status == "completed":
            total_sum += float(pay.amount)

    # Jami
    last = len(rows) + 5
    ws.cell(row=last, column=3, value="JAMI:").font = Font(bold=True)
    ws.cell(row=last, column=4, value=total_sum).font = Font(bold=True)

    return _to_bytes(wb)


# ─── 2. Davomat hisoboti ──────────────────────────────────────────────

async def attendance_report(
    db: AsyncSession,
    month: int,
    year: int,
    group_id: Optional[uuid.UUID] = None,
) -> bytes:
    """Oylik davomat hisoboti Excel."""
    from app.models.tenant import Attendance, Student, User, Group

    stmt = (
        select(
            User.first_name,
            User.last_name,
            Group.name.label("group_name"),
            func.count(Attendance.id).label("total"),
            func.count(Attendance.id).filter(Attendance.status == "present").label("present"),
            func.count(Attendance.id).filter(Attendance.status == "absent").label("absent"),
            func.count(Attendance.id).filter(Attendance.status == "late").label("late"),
            func.count(Attendance.id).filter(Attendance.status == "excused").label("excused"),
        )
        .select_from(Attendance)
        .join(Student, Attendance.student_id == Student.id)
        .join(User,    Student.user_id    == User.id)
        .join(Group,   Attendance.group_id == Group.id)
        .where(
            and_(
                extract("month", Attendance.date) == month,
                extract("year",  Attendance.date) == year,
            )
        )
        .group_by(User.first_name, User.last_name, Group.name)
        .order_by(Group.name, User.first_name)
    )

    if group_id:
        stmt = stmt.where(Attendance.group_id == group_id)

    rows = (await db.execute(stmt)).all()

    wb, ws, styles = _new_workbook(f"Davomat {month}-{year}")

    ws.merge_cells("A1:H1")
    ws["A1"].value = f"Davomat hisoboti — {month}/{year}"
    from openpyxl.styles import Font
    ws["A1"].font  = Font(bold=True, size=14)

    headers = ["#", "O'quvchi", "Guruh", "Jami", "Keldi", "Kelmadi", "Kechikdi", "Uzrli", "Foiz (%)"]
    _set_headers(ws, styles, headers, row=3)

    for i, row in enumerate(rows, start=1):
        total   = row.total or 0
        present = row.present or 0
        late    = row.late or 0
        pct     = round((present + late) / total * 100, 1) if total else 0

        _set_row(ws, styles, [
            i,
            f"{row.first_name} {row.last_name or ''}".strip(),
            row.group_name,
            total, present, row.absent or 0, late, row.excused or 0, pct,
        ], row=i + 3)

    return _to_bytes(wb)


# ─── 3. Qarzdorlar ro'yxati ───────────────────────────────────────────

async def debtors_report(db: AsyncSession) -> bytes:
    """Qarzdorlar ro'yxati Excel."""
    from app.models.tenant import Student, User, StudentGroup, Group

    stmt = (
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(and_(Student.balance < 0, Student.is_active == True))
        .order_by(Student.balance)
    )
    rows = (await db.execute(stmt)).all()

    wb, ws, styles = _new_workbook("Qarzdorlar")
    ws["A1"].value = f"Qarzdorlar ro'yxati — {date.today().strftime('%d.%m.%Y')}"
    from openpyxl.styles import Font
    ws["A1"].font  = Font(bold=True, size=14)

    headers = ["#", "O'quvchi", "Telefon", "Qarz (so'm)", "Guruhlar"]
    _set_headers(ws, styles, headers, row=3)

    for i, (st, u) in enumerate(rows, start=1):
        # Guruhlarini olish
        g_stmt = (
            select(Group.name)
            .join(StudentGroup, StudentGroup.group_id == Group.id)
            .where(and_(StudentGroup.student_id == st.id, StudentGroup.is_active == True))
        )
        groups = ", ".join(r[0] for r in (await db.execute(g_stmt)).all())

        _set_row(ws, styles, [
            i,
            f"{u.first_name} {u.last_name or ''}".strip(),
            u.phone or "—",
            abs(float(st.balance)),
            groups or "—",
        ], row=i + 3)

    return _to_bytes(wb)


# ─── 4. O'qituvchi ish haqi ───────────────────────────────────────────

async def teacher_salary_report(
    db: AsyncSession,
    month: int,
    year: int,
) -> bytes:
    """Barcha o'qituvchilar ish haqi hisoboti."""
    from app.models.tenant import Teacher, User, Group, Attendance
    from sqlalchemy import extract

    stmt = (
        select(Teacher, User)
        .join(User, Teacher.user_id == User.id)
        .where(Teacher.is_active == True)
        .order_by(User.first_name)
    )
    rows = (await db.execute(stmt)).all()

    wb, ws, styles = _new_workbook(f"Ish haqi {month}-{year}")
    ws["A1"].value = f"O'qituvchilar ish haqi — {month}/{year}"
    from openpyxl.styles import Font
    ws["A1"].font  = Font(bold=True, size=14)

    headers = ["#", "O'qituvchi", "Tur", "Miqdor", "Guruhlar", "Darslar", "Hisoblangan"]
    _set_headers(ws, styles, headers, row=3)

    for i, (teacher, user) in enumerate(rows, start=1):
        # Guruhlar soni
        g_cnt = (await db.execute(
            select(func.count(Group.id)).where(
                and_(Group.teacher_id == teacher.id, Group.status == "active")
            )
        )).scalar_one()

        # Darslar soni (davomat yozuvlari)
        l_cnt = (await db.execute(
            select(func.count(Attendance.id)).where(
                and_(
                    Attendance.teacher_id == teacher.id,
                    extract("month", Attendance.date) == month,
                    extract("year",  Attendance.date) == year,
                )
            )
        )).scalar_one()

        salary = float(teacher.salary_amount or 0)
        calculated = (
            salary if teacher.salary_type == "fixed"
            else salary * l_cnt if teacher.salary_type == "per_lesson"
            else 0
        )

        _set_row(ws, styles, [
            i,
            f"{user.first_name} {user.last_name or ''}".strip(),
            teacher.salary_type or "—",
            salary,
            g_cnt,
            l_cnt,
            calculated,
        ], row=i + 3)

    return _to_bytes(wb)
