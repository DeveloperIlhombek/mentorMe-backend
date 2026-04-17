"""app/api/v1/admin/marketing.py — Marketing endpointlari."""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_tenant_session, require_admin, require_teacher
from app.models.tenant.marketing import Invitation, Certificate
from app.models.tenant.student import Student
from app.models.tenant.user import User
from app.models.tenant.group import Group
from app.models.tenant.student import StudentGroup
from app.schemas import ok
from app.services import marketing as mkt

router = APIRouter(prefix="/marketing", tags=["marketing"])


# ─── Tenant ma'lumotlarini olish ─────────────────────────────────────

async def _get_tenant_info(db: AsyncSession) -> dict:
    """Request context dan tenant ma'lumotlarini olish."""
    try:
        from sqlalchemy import text
        result = await db.execute(text("SELECT current_schema()"))
        schema = result.scalar_one()
        # schema_name → slug
        slug = schema.replace("tenant_", "").replace("_", "-")

        from sqlalchemy import text as t2
        row = await db.execute(
            t2("SELECT name, phone, brand_color FROM public.tenants WHERE slug = :slug"),
            {"slug": slug}
        )
        tenant = row.first()
        if tenant:
            return {
                "name":        tenant[0] or "O'quv Markaz",
                "phone":       tenant[1] or "",
                "brand_color": tenant[2] or "#3B82F6",
            }
    except Exception:
        pass
    return {"name": "O'quv Markaz", "phone": "", "brand_color": "#3B82F6"}


# ─── Schemas ─────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name:                       str
    type:                       str   = "referral"
    referrer_reward_type:       str   = "bonus_sum"
    referrer_reward_value:      float = Field(ge=0, default=0)
    new_student_discount_type:  str   = "percent"
    new_student_discount_value: float = Field(ge=0, default=0)
    description:   Optional[str]     = None
    max_uses:      Optional[int]      = None
    starts_at:     Optional[datetime] = None
    ends_at:       Optional[datetime] = None


class InvitationBulkCreate(BaseModel):
    """Ko'p studentlar yoki guruh uchun taklifnoma."""
    student_ids:    Optional[List[uuid.UUID]] = None   # aniq studentlar
    group_id:       Optional[uuid.UUID]       = None   # guruh bo'yicha (hammasi)
    campaign_id:    Optional[uuid.UUID]       = None
    discount_type:  str   = "percent"
    discount_value: float = Field(ge=0, default=0)
    expires_days:   Optional[int] = 30
    promo_text:     Optional[str] = None   # Admin yozadigan jalb matni


class CertificateBulkCreate(BaseModel):
    """Ko'p studentlar uchun sertifikat."""
    student_ids:  Optional[List[uuid.UUID]] = None
    group_id:     Optional[uuid.UUID]       = None
    title:        str
    cert_type:    str = "course"
    description:  Optional[str] = None


class ResolveChurn(BaseModel):
    action_taken: str


class UseCode(BaseModel):
    code:           str
    new_student_id: uuid.UUID


# ─── Kampaniyalar ────────────────────────────────────────────────────

@router.get("/campaigns")
async def list_campaigns(
    active_only: bool    = Query(False),
    db: AsyncSession     = Depends(get_tenant_session),
    _:  dict             = Depends(require_admin),
):
    return ok(await mkt.get_campaigns(db, active_only))


@router.post("/campaigns", status_code=201)
async def create_campaign(
    data: CampaignCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_admin),
):
    result = await mkt.create_campaign(
        db,
        name                       = data.name,
        type                       = data.type,
        referrer_reward_type       = data.referrer_reward_type,
        referrer_reward_value      = data.referrer_reward_value,
        new_student_discount_type  = data.new_student_discount_type,
        new_student_discount_value = data.new_student_discount_value,
        description                = data.description,
        max_uses                   = data.max_uses,
        starts_at                  = data.starts_at,
        ends_at                    = data.ends_at,
        created_by                 = uuid.UUID(tkn["sub"]),
    )
    return ok(result)


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID,
    data: CampaignCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    from app.models.tenant.marketing import Campaign
    camp = (await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )).scalar_one_or_none()
    if not camp:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(404, "NOT_FOUND", "Kampaniya topilmadi")
    for field, value in data.model_dump(exclude_none=True).items():
        if hasattr(camp, field):
            setattr(camp, field, value)
    await db.commit()
    await db.refresh(camp)
    from app.services.marketing import _campaign_dict
    return ok(_campaign_dict(camp))


@router.post("/campaigns/{campaign_id}/toggle")
async def toggle_campaign(
    campaign_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_admin),
):
    return ok(await mkt.toggle_campaign(db, campaign_id))


@router.delete("/campaigns/{campaign_id}", status_code=200)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_admin),
):
    from app.models.tenant.marketing import Campaign
    camp = (await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )).scalar_one_or_none()
    if camp:
        await db.delete(camp)
        await db.commit()
    return ok({"message": "O'chirildi"})


# ─── Referal ─────────────────────────────────────────────────────────

@router.get("/referrals/{student_id}")
async def get_referral(
    student_id:  uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    code  = await mkt.get_or_create_referral_code(db, student_id)
    stats = await mkt.get_referral_stats(db, student_id)
    return ok({**code, **stats})


@router.post("/referrals/use")
async def use_referral(
    data: UseCode,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    result = await mkt.use_referral_code(db, data.code, data.new_student_id)
    return ok(result)


# ─── Taklifnoma ───────────────────────────────────────────────────────

@router.get("/invitations")
async def list_invitations(
    student_id:  Optional[uuid.UUID] = Query(None),
    campaign_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession                 = Depends(get_tenant_session),
    _:  dict                         = Depends(require_teacher),
):
    return ok(await mkt.get_invitations(db, student_id))


@router.post("/invitations/generate")
async def generate_invitations_bulk(
    data: InvitationBulkCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
    tkn:  dict         = Depends(require_admin),
):
    """
    Ko'p studentlar yoki butun guruh uchun taklifnoma yaratish.
    student_ids yoki group_id berish kerak.
    """
    tenant_info = await _get_tenant_info(db)

    # Student ID larni to'plash
    student_ids: List[uuid.UUID] = []

    if data.group_id:
        rows = (await db.execute(
            select(StudentGroup.student_id).where(
                StudentGroup.group_id == data.group_id,
                StudentGroup.is_active == True,
            )
        )).scalars().all()
        student_ids = list(rows)
    elif data.student_ids:
        student_ids = data.student_ids

    if not student_ids:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(400, "NO_STUDENTS", "O'quvchi tanlanmadi")

    created = []
    errors  = []

    for sid in student_ids:
        try:
            result = await mkt.generate_invitation(
                db,
                student_id     = sid,
                campaign_id    = data.campaign_id,
                discount_type  = data.discount_type,
                discount_value = data.discount_value,
                expires_days   = data.expires_days,
                center_name    = tenant_info["name"],
                center_phone   = tenant_info["phone"],
                brand_color    = tenant_info["brand_color"],
                promo_text     = data.promo_text,
            )
            result.pop("pdf_bytes", None)
            created.append(result)
        except Exception as e:
            errors.append({"student_id": str(sid), "error": str(e)})

    return ok({
        "created": created,
        "errors":  errors,
        "total":   len(created),
    })


@router.get("/invitations/{invitation_id}/pdf")
async def download_invitation_pdf(
    invitation_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
):
    """Taklifnoma PDFni to'g'ridan yuklab olish (auth shart emas)."""
    inv = (await db.execute(
        select(Invitation).where(Invitation.id == invitation_id)
    )).scalar_one_or_none()
    if not inv:
        return Response(status_code=404)

    row = (await db.execute(
        select(Student, User)
        .join(User, Student.user_id == User.id)
        .where(Student.id == inv.student_id)
    )).first()
    student_name = f"{row[1].first_name} {row[1].last_name or ''}".strip() if row else "O'quvchi"

    tenant_info = await _get_tenant_info(db)

    from app.services.pdf_generator import generate_invitation_pdf
    pdf_bytes = generate_invitation_pdf(
        center_name    = tenant_info["name"],
        center_phone   = tenant_info["phone"],
        student_name   = student_name,
        invite_code    = inv.code,
        discount_type  = inv.discount_type,
        discount_value = float(inv.discount_value),
        expires_at     = inv.expires_at,
        brand_color    = tenant_info["brand_color"],
        promo_text     = inv.promo_text if hasattr(inv, 'promo_text') else None,
    )

    import io
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invitation-{inv.code}.pdf"},
    )


@router.post("/invitations/use")
async def use_invitation(
    data: UseCode,
    db:   AsyncSession = Depends(get_tenant_session),
    _:    dict         = Depends(require_admin),
):
    result = await mkt.use_invitation(db, data.code, data.new_student_id)
    return ok(result)


@router.delete("/invitations/{invitation_id}", status_code=200)
async def delete_invitation(
    invitation_id: uuid.UUID,
    db:  AsyncSession = Depends(get_tenant_session),
    _:   dict         = Depends(require_admin),
):
    inv = (await db.execute(
        select(Invitation).where(Invitation.id == invitation_id)
    )).scalar_one_or_none()
    if inv:
        await db.delete(inv)
        await db.commit()
    return ok({"message": "O'chirildi"})


# ─── Sertifikat ───────────────────────────────────────────────────────

@router.get("/certificates")
async def list_certificates(
    student_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession                = Depends(get_tenant_session),
    _:  dict                        = Depends(require_admin),
):
    return ok(await mkt.get_certificates(db, student_id))


@router.post("/certificates/generate", status_code=201)
async def generate_certificates_bulk(
    data: CertificateBulkCreate,
    db:   AsyncSession = Depends(get_tenant_session),
    tkn:  dict         = Depends(require_admin),
):
    """Ko'p studentlar yoki guruh uchun sertifikat yaratish."""
    tenant_info = await _get_tenant_info(db)
    issued_by   = uuid.UUID(tkn["sub"])

    # Student ID larni to'plash
    student_ids: List[uuid.UUID] = []

    if data.group_id:
        rows = (await db.execute(
            select(StudentGroup.student_id).where(
                StudentGroup.group_id  == data.group_id,
                StudentGroup.is_active == True,
            )
        )).scalars().all()
        student_ids = list(rows)
    elif data.student_ids:
        student_ids = data.student_ids

    if not student_ids:
        from app.core.exceptions import EduSaaSException
        raise EduSaaSException(400, "NO_STUDENTS", "O'quvchi tanlanmadi")

    created = []
    errors  = []

    for sid in student_ids:
        try:
            result = await mkt.issue_certificate(
                db,
                student_id  = sid,
                title       = data.title,
                cert_type   = data.cert_type,
                description = data.description,
                issued_by   = issued_by,
                center_name = tenant_info["name"],
                brand_color = tenant_info["brand_color"],
            )
            result.pop("pdf_bytes", None)
            created.append(result)
        except Exception as e:
            errors.append({"student_id": str(sid), "error": str(e)})

    return ok({"created": created, "errors": errors, "total": len(created)})


@router.get("/certificates/{cert_id}/pdf")
async def download_certificate_pdf(
    cert_id: uuid.UUID,
    db: AsyncSession = Depends(get_tenant_session),
):
    """Sertifikat PDFni yuklab olish (public)."""
    row = (await db.execute(
        select(Certificate, Student, User)
        .join(Student, Certificate.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .where(Certificate.id == cert_id)
    )).first()
    if not row:
        return Response(status_code=404)

    cert, s, u = row
    student_name = f"{u.first_name} {u.last_name or ''}".strip()
    tenant_info  = await _get_tenant_info(db)

    from app.services.pdf_generator import generate_certificate_pdf
    pdf_bytes = generate_certificate_pdf(
        center_name  = tenant_info["name"],
        student_name = student_name,
        title        = cert.title,
        description  = cert.description,
        issued_at    = cert.issued_at,
        verify_code  = cert.verify_code,
        brand_color  = tenant_info["brand_color"],
    )

    import io
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cert-{cert.verify_code}.pdf"},
    )


@router.get("/certificates/verify/{verify_code}")
async def verify_certificate(
    verify_code: str,
    db: AsyncSession = Depends(get_tenant_session),
):
    result = await mkt.verify_certificate(db, verify_code)
    if not result:
        return ok({"valid": False})
    return ok(result)


# ─── Churn Risk ───────────────────────────────────────────────────────

@router.get("/churn-risks")
async def list_churn_risks(
    level:    Optional[str] = Query(None),
    resolved: bool          = Query(False),
    db: AsyncSession        = Depends(get_tenant_session),
    _:  dict                = Depends(require_admin),
):
    return ok(await mkt.get_churn_risks(db, level, resolved))


@router.post("/churn-risks/calculate")
async def recalculate_churn(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    count = await mkt.calculate_churn_risks(db)
    return ok({"calculated": count})


@router.post("/churn-risks/{risk_id}/resolve")
async def resolve_risk(
    risk_id: uuid.UUID,
    data:    ResolveChurn,
    db:      AsyncSession = Depends(get_tenant_session),
    _:       dict         = Depends(require_admin),
):
    result = await mkt.resolve_churn_risk(db, risk_id, data.action_taken)
    return ok(result)


# ─── Statistika ───────────────────────────────────────────────────────

@router.get("/stats")
async def marketing_stats(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_admin),
):
    return ok(await mkt.get_marketing_stats(db))


# ─── Guruhlar ro'yxati (modal uchun) ─────────────────────────────────

@router.get("/groups")
async def get_groups_for_marketing(
    db: AsyncSession = Depends(get_tenant_session),
    _:  dict         = Depends(require_teacher),
):
    """Marketing modali uchun faol guruhlar ro'yxati."""
    rows = (await db.execute(
        select(Group).where(Group.status == "active").order_by(Group.name)
    )).scalars().all()
    return ok([{
        "id":            str(g.id),
        "name":          g.name,
        "subject":       g.subject,
        "student_count": g.student_count if hasattr(g, 'student_count') else 0,
    } for g in rows])
