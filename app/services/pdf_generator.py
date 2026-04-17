"""app/services/pdf_generator.py — Taklifnoma va Sertifikat PDF yaratish."""
import io
import uuid
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


# ─── Taklifnoma PDF ───────────────────────────────────────────────────

def generate_invitation_pdf(
    center_name:     str,
    center_phone:    str,
    student_name:    str,
    invite_code:     str,
    discount_type:   str,          # percent | fixed
    discount_value:  float,
    expires_at:      Optional[datetime] = None,
    brand_color:     str = "#3B82F6",
    promo_text:      Optional[str] = None,
) -> bytes:
    """
    O'quvchi uchun taklifnoma PDF.
    QR kod o'rniga yirik text kod ko'rsatiladi (qrcode kutubxonasisiz).
    """
    buf = io.BytesIO()
    c   = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # ── Fon ──────────────────────────────────────────────────────────
    r, g, b = _hex_to_rgb(brand_color)
    c.setFillColorRGB(r, g, b)
    c.rect(0, H - 3*cm, W, 3*cm, fill=1, stroke=0)

    # ── Sarlavha ─────────────────────────────────────────────────────
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(W / 2, H - 1.6*cm, center_name)
    c.setFont("Helvetica", 11)
    c.drawCentredString(W / 2, H - 2.3*cm, center_phone)

    # ── Asosiy kontent ───────────────────────────────────────────────
    y = H - 4.5*cm

    # "MAXSUS TAKLIF" banner
    c.setFillColorRGB(r * 0.85, g * 0.85, b * 0.85)
    c.roundRect(2*cm, y - 1.2*cm, W - 4*cm, 1.5*cm, 8, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W / 2, y - 0.55*cm, "MAXSUS TAKLIF")
    y -= 2.5*cm

    # O'quvchi ismi
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica", 12)
    c.drawCentredString(W / 2, y, "Hurmatli")
    y -= 0.6*cm
    c.setFont("Helvetica-Bold", 18)
    c.setFillColorRGB(r, g, b)
    c.drawCentredString(W / 2, y, student_name)
    y -= 1.5*cm

    # Chegirma bloki
    c.setFillColorRGB(0.97, 0.97, 0.97)
    c.roundRect(2*cm, y - 2.5*cm, W - 4*cm, 3*cm, 10, fill=1, stroke=0)
    c.setStrokeColorRGB(r, g, b)
    c.setLineWidth(1.5)
    c.roundRect(2*cm, y - 2.5*cm, W - 4*cm, 3*cm, 10, fill=0, stroke=1)

    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica", 11)
    c.drawCentredString(W / 2, y - 0.6*cm, "Ushbu taklifnoma bilan")
    c.setFont("Helvetica-Bold", 28)
    c.setFillColorRGB(r, g, b)
    if discount_type == "percent":
        discount_text = f"{int(discount_value)}% CHEGIRMA"
    else:
        discount_text = f"{int(discount_value):,} SO'M CHEGIRMA"
    c.drawCentredString(W / 2, y - 1.4*cm, discount_text)
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(W / 2, y - 2.1*cm, "birinchi oylik to'lovga")
    y -= 4*cm

    # Promo matn (agar mavjud bo'lsa)
    if promo_text:
        c.setFillColorRGB(0.15, 0.15, 0.15)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(W / 2, y, promo_text[:80])
        y -= 1*cm

    # Kod bloki
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W / 2, y, "TAKLIFNOMA KODI:")
    y -= 0.8*cm

    # Kod ramkasi
    c.setFillColorRGB(r, g, b)
    c.roundRect(W/2 - 4*cm, y - 1.2*cm, 8*cm, 1.5*cm, 6, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(W / 2, y - 0.55*cm, invite_code)
    y -= 2.5*cm

    # Muddati
    if expires_at:
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.6, 0.6, 0.6)
        exp_str = expires_at.strftime("%d.%m.%Y")
        c.drawCentredString(W / 2, y, f"Amal qilish muddati: {exp_str}")
        y -= 1*cm

    # Qo'llash tartibi
    y -= 0.5*cm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.drawString(2*cm, y, "Qo'llash tartibi:")
    steps = [
        "1. O'quv markazimizga tashrif buyuring",
        "2. Ro'yxatdan o'tishda ushbu kodni ko'rsating",
        "3. Chegirma birinchi oylik to'lovga qo'llaniladi",
    ]
    for step in steps:
        y -= 0.55*cm
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(2.5*cm, y, step)

    # ── Footer ───────────────────────────────────────────────────────
    c.setFillColorRGB(r, g, b)
    c.rect(0, 0, W, 1.2*cm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, 0.45*cm,
        f"{center_name}  |  Kod: {invite_code}  |  "
        + (f"Muddat: {expires_at.strftime('%d.%m.%Y')}" if expires_at else "Muddatsiz"))

    c.save()
    return buf.getvalue()


# ─── Sertifikat PDF ───────────────────────────────────────────────────

def generate_certificate_pdf(
    center_name:   str,
    student_name:  str,
    title:         str,
    description:   Optional[str] = None,
    issued_at:     Optional[datetime] = None,
    verify_code:   str = "",
    brand_color:   str = "#3B82F6",
) -> bytes:
    buf = io.BytesIO()
    # A4 landscape
    W, H = A4[1], A4[0]
    c = canvas.Canvas(buf, pagesize=(W, H))

    r, g, b = _hex_to_rgb(brand_color)

    # ── Chiziq ramka ─────────────────────────────────────────────────
    c.setStrokeColorRGB(r, g, b)
    c.setLineWidth(4)
    c.rect(1.2*cm, 1.2*cm, W - 2.4*cm, H - 2.4*cm, fill=0, stroke=1)
    c.setLineWidth(1)
    c.rect(1.5*cm, 1.5*cm, W - 3*cm, H - 3*cm, fill=0, stroke=1)

    # ── Markaz nomi (yuqori) ─────────────────────────────────────────
    c.setFillColorRGB(r, g, b)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(W / 2, H - 3*cm, center_name.upper())

    # ── "SERTIFIKAT" ─────────────────────────────────────────────────
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.setFont("Helvetica-Bold", 48)
    c.drawCentredString(W / 2, H - 6*cm, "SERTIFIKAT")

    # Bezak chiziq
    c.setStrokeColorRGB(r, g, b)
    c.setLineWidth(2)
    c.line(W/2 - 6*cm, H - 6.6*cm, W/2 + 6*cm, H - 6.6*cm)

    # ── "Taqdim etiladi" ─────────────────────────────────────────────
    c.setFont("Helvetica", 13)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(W / 2, H - 7.8*cm, "Mazkur sertifikat")

    # ── O'quvchi ismi ────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 32)
    c.setFillColorRGB(r, g, b)
    c.drawCentredString(W / 2, H - 9.2*cm, student_name)

    # ── Kurs nomi ────────────────────────────────────────────────────
    c.setFont("Helvetica", 13)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(W / 2, H - 10.4*cm, "muvaffaqiyatli tamomlashi munosabati bilan")
    c.setFont("Helvetica-Bold", 18)
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.drawCentredString(W / 2, H - 11.4*cm, f'"{title}"')

    if description:
        c.setFont("Helvetica", 11)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawCentredString(W / 2, H - 12.2*cm, description)

    # ── Taqdim etiladi ───────────────────────────────────────────────
    issued = issued_at or datetime.now()
    c.setFont("Helvetica", 12)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(W / 2, H - 13.4*cm,
        f"taqdim etildi  |  {issued.strftime('%d.%m.%Y')}")

    # ── Imzo chizig'i ────────────────────────────────────────────────
    c.setStrokeColorRGB(0.3, 0.3, 0.3)
    c.setLineWidth(0.5)
    c.line(W/2 - 4*cm, H - 15*cm, W/2 + 4*cm, H - 15*cm)
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(W / 2, H - 15.5*cm, "Direktor imzosi")

    # ── Verify kodi ──────────────────────────────────────────────────
    if verify_code:
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.7, 0.7, 0.7)
        c.drawCentredString(W / 2, 2*cm, f"Tekshirish kodi: {verify_code}")

    c.save()
    return buf.getvalue()


# ─── Helper ───────────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255
    return r, g, b
