"""app/services/marketing.py — Marketing biznes logikasi."""
import secrets
import string
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant.attendance import Attendance
from app.models.tenant.marketing import (
    Campaign,
    Certificate,
    ChurnRisk,
    Invitation,
    ReferralCode,
    ReferralUse,
)
from app.models.tenant.payment import Payment
from app.models.tenant.student import Student
from app.models.tenant.user import User

# ─── KAMPANIYALAR ─────────────────────────────────────────────────────

async def get_campaigns(db: AsyncSession, active_only: bool = False) -> List[dict]:
    stmt = select(Campaign).order_by(desc(Campaign.created_at))
    if active_only:
        stmt = stmt.where(Campaign.is_active == True)
    rows = (await db.execute(stmt)).scalars().all()
    return [_campaign_dict(c) for c in rows]


async def create_campaign(
    db:         AsyncSession,
    name:       str,
    type:       str,
    referrer_reward_type:       str   = "bonus_sum",
    referrer_reward_value:      float = 0,
    new_student_discount_type:  str   = "percent",
    new_student_discount_value: float = 0,
    description: Optional[str]  = None,
    max_uses:    Optional[int]   = None,
    starts_at:   Optional[datetime] = None,
    ends_at:     Optional[datetime] = None,
    created_by:  Optional[uuid.UUID] = None,
) -> dict:
    camp = Campaign(
        name=name, type=type, description=description,
        referrer_reward_type=referrer_reward_type,
        referrer_reward_value=Decimal(str(referrer_reward_value)),
        new_student_discount_type=new_student_discount_type,
        new_student_discount_value=Decimal(str(new_student_discount_value)),
        max_uses=max_uses, starts_at=starts_at, ends_at=ends_at,
        created_by=created_by,
    )
    db.add(camp)
    await db.commit()
    await db.refresh(camp)
    return _campaign_dict(camp)


async def toggle_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> dict:
    camp = (await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )).scalar_one_or_none()
    if not camp:
        raise ValueError("Kampaniya topilmadi")
    camp.is_active = not camp.is_active
    await db.commit()
    await db.refresh(camp)
    return _campaign_dict(camp)


# ─── REFERAL KODLAR ───────────────────────────────────────────────────

def _make_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


async def get_or_create_referral_code(
    db: AsyncSession,
    student_id: uuid.UUID,
    campaign_id: Optional[uuid.UUID] = None,
) -> dict:
    existing = (await db.execute(
        select(ReferralCode).where(ReferralCode.student_id == student_id)
    )).scalar_one_or_none()
    if existing:
        return _ref_code_dict(existing)

    # Noyob kod yaratish
    for _ in range(10):
        code = _make_code()
        clash = (await db.execute(
            select(ReferralCode).where(ReferralCode.code == code)
        )).scalar_one_or_none()
        if not clash:
            break

    rc = ReferralCode(student_id=student_id, campaign_id=campaign_id, code=code)
    db.add(rc)
    await db.commit()
    await db.refresh(rc)
    return _ref_code_dict(rc)


async def use_referral_code(
    db:             AsyncSession,
    code:           str,
    new_student_id: uuid.UUID,
) -> dict:
    """Yangi o'quvchi ro'yxatdan o'tishda referal kod ishlatadi."""
    rc = (await db.execute(
        select(ReferralCode).where(ReferralCode.code == code)
    )).scalar_one_or_none()
    if not rc:
        raise ValueError("Kod topilmadi")

    # Oldin ishlatilganmi?
    used = (await db.execute(
        select(ReferralUse).where(
            ReferralUse.code_id == rc.id,
            ReferralUse.new_student_id == new_student_id,
        )
    )).scalar_one_or_none()
    if used:
        raise ValueError("Bu kod allaqachon ishlatilgan")

    # O'ziga ishlatishi mumkin emas
    if rc.student_id == new_student_id:
        raise ValueError("O'z kodingizni ishlatib bo'lmaydi")

    # Kampaniya chegirma qiymatlari
    referrer_bonus       = Decimal("0")
    new_student_discount = Decimal("0")

    if rc.campaign_id:
        camp = (await db.execute(
            select(Campaign).where(Campaign.id == rc.campaign_id, Campaign.is_active == True)
        )).scalar_one_or_none()
        if camp:
            referrer_bonus       = Decimal(str(camp.referrer_reward_value or 0))
            new_student_discount = Decimal(str(camp.new_student_discount_value or 0))

    ru = ReferralUse(
        code_id              = rc.id,
        new_student_id       = new_student_id,
        referrer_bonus       = referrer_bonus,
        new_student_discount = new_student_discount,
    )
    db.add(ru)
    rc.total_uses   += 1
    rc.total_earned = Decimal(str(rc.total_earned)) + referrer_bonus
    await db.commit()
    return {
        "referrer_bonus":       float(referrer_bonus),
        "new_student_discount": float(new_student_discount),
        "code":                 code,
    }


async def get_referral_stats(db: AsyncSession, student_id: uuid.UUID) -> dict:
    rc = (await db.execute(
        select(ReferralCode).where(ReferralCode.student_id == student_id)
    )).scalar_one_or_none()
    if not rc:
        return {"code": None, "total_uses": 0, "total_earned": 0, "uses": []}

    uses = (await db.execute(
        select(ReferralUse, User)
        .join(Student, ReferralUse.new_student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .where(ReferralUse.code_id == rc.id)
        .order_by(desc(ReferralUse.created_at))
    )).all()

    return {
        "code":         rc.code,
        "total_uses":   rc.total_uses,
        "total_earned": float(rc.total_earned),
        "uses": [{
            "student_name": f"{u.first_name} {u.last_name or ''}".strip(),
            "bonus":        float(r.referrer_bonus),
            "status":       r.status,
            "date":         r.created_at.isoformat() if r.created_at else None,
        } for r, u in uses],
    }


# ─── TAKLIFNOMA ───────────────────────────────────────────────────────

async def generate_invitation(
    db:             AsyncSession,
    student_id:     uuid.UUID,
    campaign_id:    Optional[uuid.UUID],
    discount_type:  str   = "percent",
    discount_value: float = 0,
    expires_days:   Optional[int] = 30,
    center_name:    str   = "",
    center_phone:   str   = "",
    brand_color:    str   = "#3B82F6",
    promo_text:     Optional[str] = None,
) -> dict:
    from app.services.pdf_generator import generate_invitation_pdf

    # O'quvchi ma'lumoti
    student = (await db.execute(
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.id == student_id)
    )).first()
    if not student:
        raise ValueError("O'quvchi topilmadi")
    s, u = student
    student_name = f"{u.first_name} {u.last_name or ''}".strip()

    # Noyob kod
    for _ in range(10):
        code = "INV-" + _make_code(6)
        clash = (await db.execute(
            select(Invitation).where(Invitation.code == code)
        )).scalar_one_or_none()
        if not clash:
            break

    expires_at = datetime.utcnow() + timedelta(days=expires_days) if expires_days else None

    inv = Invitation(
        student_id     = student_id,
        campaign_id    = campaign_id,
        code           = code,
        discount_type  = discount_type,
        discount_value = Decimal(str(discount_value)),
        expires_at     = expires_at,
        promo_text     = promo_text,
    )
    db.add(inv)
    await db.flush()

    # PDF yaratish
    pdf_bytes = generate_invitation_pdf(
        center_name    = center_name,
        center_phone   = center_phone,
        student_name   = student_name,
        invite_code    = code,
        discount_type  = discount_type,
        discount_value = discount_value,
        expires_at     = expires_at,
        brand_color    = brand_color,
        promo_text     = promo_text,
    )

    # S3 ga yuklash (xato bo'lsa o'tkazib yuboramiz)
    pdf_url = None
    try:
        from app.services.storage import upload_bytes
        pdf_url = await upload_bytes(
            pdf_bytes,
            key=f"invitations/{inv.id}.pdf",
            content_type="application/pdf",
        )
        inv.pdf_url = pdf_url
    except Exception:
        pass

    await db.commit()
    await db.refresh(inv)

    return {
        **_inv_dict(inv),
        "student_name": student_name,
        "pdf_bytes":    pdf_bytes,   # endpoint to'g'ridan response qaytaradi
    }


async def use_invitation(
    db:            AsyncSession,
    code:          str,
    new_student_id: uuid.UUID,
) -> dict:
    inv = (await db.execute(
        select(Invitation).where(
            Invitation.code      == code,
            Invitation.is_active == True,
            Invitation.used_by   == None,
        )
    )).scalar_one_or_none()
    if not inv:
        raise ValueError("Kod topilmadi yoki allaqachon ishlatilgan")
    if inv.expires_at and inv.expires_at < datetime.utcnow():
        raise ValueError("Kod muddati tugagan")

    inv.used_by = new_student_id
    inv.used_at = datetime.utcnow()
    await db.commit()
    return {
        "discount_type":  inv.discount_type,
        "discount_value": float(inv.discount_value),
    }


async def get_invitations(
    db:         AsyncSession,
    student_id: Optional[uuid.UUID] = None,
) -> List[dict]:
    stmt = (
        select(Invitation, User)
        .join(Student, Invitation.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .order_by(desc(Invitation.created_at))
    )
    if student_id:
        stmt = stmt.where(Invitation.student_id == student_id)
    rows = (await db.execute(stmt)).all()
    return [{
        **_inv_dict(inv),
        "student_name": f"{u.first_name} {u.last_name or ''}".strip(),
    } for inv, u in rows]


# ─── SERTIFIKAT ───────────────────────────────────────────────────────

async def issue_certificate(
    db:          AsyncSession,
    student_id:  uuid.UUID,
    title:       str,
    cert_type:   str   = "course",
    description: Optional[str] = None,
    issued_by:   Optional[uuid.UUID] = None,
    center_name: str   = "",
    brand_color: str   = "#3B82F6",
) -> dict:
    from app.services.pdf_generator import generate_certificate_pdf

    student = (await db.execute(
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.id == student_id)
    )).first()
    if not student:
        raise ValueError("O'quvchi topilmadi")
    s, u = student
    student_name = f"{u.first_name} {u.last_name or ''}".strip()

    # Noyob verify kodi
    verify_code = _make_code(12)

    cert = Certificate(
        student_id       = student_id,
        certificate_type = cert_type,
        title            = title,
        description      = description,
        issued_by        = issued_by,
        verify_code      = verify_code,
    )
    db.add(cert)
    await db.flush()

    # PDF
    pdf_bytes = generate_certificate_pdf(
        center_name  = center_name,
        student_name = student_name,
        title        = title,
        description  = description,
        issued_at    = datetime.utcnow(),
        verify_code  = verify_code,
        brand_color  = brand_color,
    )

    pdf_url = None
    try:
        from app.services.storage import upload_bytes
        pdf_url = await upload_bytes(
            pdf_bytes,
            key=f"certificates/{cert.id}.pdf",
            content_type="application/pdf",
        )
        cert.pdf_url = pdf_url
    except Exception:
        pass

    await db.commit()
    await db.refresh(cert)

    return {
        **_cert_dict(cert),
        "student_name": student_name,
        "pdf_bytes":    pdf_bytes,
    }


async def get_certificates(
    db:         AsyncSession,
    student_id: Optional[uuid.UUID] = None,
) -> List[dict]:
    stmt = (
        select(Certificate, User)
        .join(Student, Certificate.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .order_by(desc(Certificate.issued_at))
    )
    if student_id:
        stmt = stmt.where(Certificate.student_id == student_id)
    rows = (await db.execute(stmt)).all()
    return [{
        **_cert_dict(cert),
        "student_name": f"{u.first_name} {u.last_name or ''}".strip(),
    } for cert, u in rows]


async def verify_certificate(db: AsyncSession, verify_code: str) -> Optional[dict]:
    row = (await db.execute(
        select(Certificate, Student, User)
        .join(Student, Certificate.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .where(Certificate.verify_code == verify_code)
    )).first()
    if not row:
        return None
    cert, s, u = row
    return {
        **_cert_dict(cert),
        "student_name": f"{u.first_name} {u.last_name or ''}".strip(),
        "valid": True,
    }


# ─── CHURN RISK ───────────────────────────────────────────────────────

async def calculate_churn_risks(db: AsyncSession) -> int:
    """Barcha faol o'quvchilar uchun churn risk hisoblash. Celery chaqiradi."""
    today     = date.today()
    two_weeks = today - timedelta(days=14)

    students = (await db.execute(
        select(Student).where(Student.is_active == True)
    )).scalars().all()

    updated = 0
    for student in students:
        score, signals = await _compute_churn_score(db, student.id, today, two_weeks)
        level = (
            "critical" if score >= 75 else
            "high"     if score >= 50 else
            "medium"   if score >= 25 else
            "low"
        )

        existing = (await db.execute(
            select(ChurnRisk).where(ChurnRisk.student_id == student.id)
        )).scalar_one_or_none()

        if existing:
            existing.risk_score    = score
            existing.risk_level    = level
            existing.signals       = signals
            existing.calculated_at = datetime.utcnow()
        else:
            db.add(ChurnRisk(
                student_id    = student.id,
                risk_score    = score,
                risk_level    = level,
                signals       = signals,
            ))
        updated += 1

    await db.commit()
    return updated


async def _compute_churn_score(
    db:         AsyncSession,
    student_id: uuid.UUID,
    today:      date,
    two_weeks:  date,
) -> Tuple[float, list]:
    signals = []
    score   = 0.0

    # Signal 1: So'nggi 2 haftada davomatni tekshirish
    total_att = (await db.execute(
        select(func.count(Attendance.id)).where(
            and_(
                Attendance.student_id == student_id,
                Attendance.date >= two_weeks,
            )
        )
    )).scalar_one()

    absent_att = (await db.execute(
        select(func.count(Attendance.id)).where(
            and_(
                Attendance.student_id == student_id,
                Attendance.date >= two_weeks,
                Attendance.status == "absent",
            )
        )
    )).scalar_one()

    if total_att > 0:
        absent_pct = absent_att / total_att * 100
        if absent_pct >= 60:
            score += 40
            signals.append({"type": "high_absence", "value": f"{absent_pct:.0f}% absent"})
        elif absent_pct >= 30:
            score += 20
            signals.append({"type": "medium_absence", "value": f"{absent_pct:.0f}% absent"})
    elif total_att == 0:
        score += 30
        signals.append({"type": "no_attendance", "value": "2 haftada dars yo'q"})

    # Signal 2: To'lov kechikishi
    student = (await db.execute(
        select(Student).where(Student.id == student_id)
    )).scalar_one_or_none()

    if student and float(student.balance or 0) < 0:
        debt = abs(float(student.balance))
        if debt > 500_000:
            score += 35
            signals.append({"type": "high_debt", "value": f"{debt:,.0f} so'm qarz"})
        else:
            score += 15
            signals.append({"type": "debt", "value": f"{debt:,.0f} so'm qarz"})

    # Signal 3: 3 ketma-ket darsni o'tkazib yuborish
    last_3 = (await db.execute(
        select(Attendance.status)
        .where(Attendance.student_id == student_id)
        .order_by(desc(Attendance.date))
        .limit(3)
    )).scalars().all()

    if len(last_3) >= 3 and all(s == "absent" for s in last_3):
        score += 25
        signals.append({"type": "consecutive_absent", "value": "3 ketma-ket dars o'tkazildi"})

    return min(score, 100.0), signals


async def get_churn_risks(
    db:         AsyncSession,
    level:      Optional[str] = None,
    resolved:   bool          = False,
) -> List[dict]:
    stmt = (
        select(ChurnRisk, Student, User)
        .join(Student, ChurnRisk.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .where(
            ChurnRisk.resolved_at.is_(None) if not resolved
            else ChurnRisk.resolved_at.isnot(None)
        )
    )
    if level:
        stmt = stmt.where(ChurnRisk.risk_level == level)
    stmt = stmt.order_by(desc(ChurnRisk.risk_score))
    rows = (await db.execute(stmt)).all()

    return [{
        "id":            str(cr.id),
        "student_id":    str(cr.student_id),
        "student_name":  f"{u.first_name} {u.last_name or ''}".strip(),
        "student_phone": u.phone,
        "risk_score":    float(cr.risk_score),
        "risk_level":    cr.risk_level,
        "signals":       cr.signals or [],
        "action_taken":  cr.action_taken,
        "resolved_at":   cr.resolved_at.isoformat() if cr.resolved_at else None,
        "calculated_at": cr.calculated_at.isoformat() if cr.calculated_at else None,
    } for cr, s, u in rows]


async def resolve_churn_risk(
    db:          AsyncSession,
    risk_id:     uuid.UUID,
    action_taken: str,
) -> dict:
    cr = (await db.execute(
        select(ChurnRisk).where(ChurnRisk.id == risk_id)
    )).scalar_one_or_none()
    if not cr:
        raise ValueError("Risk topilmadi")
    cr.action_taken = action_taken
    cr.resolved_at  = datetime.utcnow()
    await db.commit()
    return {"id": str(cr.id), "resolved": True}


async def get_marketing_stats(db: AsyncSession) -> dict:
    """Dashboard uchun umumiy statistika."""
    total_refs = (await db.execute(select(func.count(ReferralCode.id)))).scalar_one()
    total_uses = (await db.execute(select(func.sum(ReferralCode.total_uses)))).scalar_one() or 0
    total_earned = (await db.execute(select(func.sum(ReferralCode.total_earned)))).scalar_one() or 0

    active_invitations = (await db.execute(
        select(func.count(Invitation.id)).where(
            Invitation.is_active == True, Invitation.used_by == None
        )
    )).scalar_one()
    used_invitations = (await db.execute(
        select(func.count(Invitation.id)).where(Invitation.used_by != None)
    )).scalar_one()

    total_certs = (await db.execute(select(func.count(Certificate.id)))).scalar_one()

    high_risk = (await db.execute(
        select(func.count(ChurnRisk.id)).where(
            ChurnRisk.risk_level.in_(["high", "critical"]),
            ChurnRisk.resolved_at.is_(None),
        )
    )).scalar_one()

    return {
        "referral": {
            "total_codes":  total_refs,
            "total_uses":   int(total_uses),
            "total_earned": float(total_earned),
        },
        "invitation": {
            "active": active_invitations,
            "used":   used_invitations,
        },
        "certificates": total_certs,
        "churn_high_risk": high_risk,
    }


# ─── Helpers ─────────────────────────────────────────────────────────

def _campaign_dict(c: Campaign) -> dict:
    return {
        "id":                         str(c.id),
        "name":                       c.name,
        "description":                c.description,
        "type":                       c.type,
        "referrer_reward_type":       c.referrer_reward_type,
        "referrer_reward_value":      float(c.referrer_reward_value or 0),
        "new_student_discount_type":  c.new_student_discount_type,
        "new_student_discount_value": float(c.new_student_discount_value or 0),
        "max_uses":                   c.max_uses,
        "used_count":                 c.used_count,
        "starts_at": c.starts_at.isoformat() if c.starts_at else None,
        "ends_at":   c.ends_at.isoformat()   if c.ends_at   else None,
        "is_active": c.is_active,
    }


def _ref_code_dict(rc: ReferralCode) -> dict:
    return {
        "id":           str(rc.id),
        "student_id":   str(rc.student_id),
        "code":         rc.code,
        "total_uses":   rc.total_uses,
        "total_earned": float(rc.total_earned),
    }


def _inv_dict(inv: Invitation) -> dict:
    return {
        "id":             str(inv.id),
        "student_id":     str(inv.student_id),
        "code":           inv.code,
        "discount_type":  inv.discount_type,
        "discount_value": float(inv.discount_value),
        "pdf_url":        inv.pdf_url,
        "used_at":        inv.used_at.isoformat() if inv.used_at else None,
        "expires_at":     inv.expires_at.isoformat() if inv.expires_at else None,
        "is_active":      inv.is_active,
        "promo_text":     getattr(inv, "promo_text", None),
    }


def _cert_dict(c: Certificate) -> dict:
    return {
        "id":               str(c.id),
        "student_id":       str(c.student_id),
        "certificate_type": c.certificate_type,
        "title":            c.title,
        "description":      c.description,
        "verify_code":      c.verify_code,
        "pdf_url":          c.pdf_url,
        "is_public":        c.is_public,
        "issued_at":        c.issued_at.isoformat() if c.issued_at else None,
    }
