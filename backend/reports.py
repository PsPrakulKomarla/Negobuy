"""Procurement report PDF export (reportlab)."""
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from auth import get_current_user
from db import get_db

router = APIRouter(prefix="/api/missions", tags=["reports"])

INK = colors.HexColor("#0a0e14")
CYAN = colors.HexColor("#00a3b4")
GREEN = colors.HexColor("#0f9d6a")
MUTE = colors.HexColor("#6b7280")


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=20, textColor=INK, spaceAfter=4))
    s.add(ParagraphStyle("Sub", fontName="Helvetica", fontSize=9, textColor=MUTE, spaceAfter=14))
    s.add(ParagraphStyle("Sec", fontName="Helvetica-Bold", fontSize=12, textColor=CYAN,
                         spaceBefore=14, spaceAfter=8))
    s.add(ParagraphStyle("Body", fontName="Helvetica", fontSize=9.5, textColor=INK, leading=14))
    s.add(ParagraphStyle("Small", fontName="Helvetica", fontSize=8, textColor=MUTE, leading=11))
    return s


@router.get("/{mission_id}/report")
async def report(mission_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    mission = await db.missions.find_one(
        {"id": mission_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    vendors = await db.vendors.find({"mission_id": mission_id}, {"_id": 0}) \
        .sort("weighted_score", -1).to_list(50)
    offers = await db.offers.find({"mission_id": mission_id}, {"_id": 0}).to_list(50)
    comparison = await db.comparisons.find_one({"mission_id": mission_id}, {"_id": 0})
    approvals = await db.approvals.find({"mission_id": mission_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(20)
    cur = mission.get("currency") or ""

    st = _styles()
    story = []
    story.append(Paragraph("NegoBuy — Procurement Report", st["H"]))
    story.append(Paragraph(
        f"{mission.get('title','')} &nbsp;·&nbsp; {user.get('organization_name','')} &nbsp;·&nbsp; "
        f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}", st["Sub"]))

    story.append(Paragraph("Requirement", st["Sec"]))
    rows = [
        ["Status", (mission.get("status") or "").replace("_", " ")],
        ["Category", mission.get("category") or "—"],
        ["Quantity", str(mission.get("quantity") or "—")],
        ["Budget", f"{cur} {mission.get('budget'):,.0f}" if mission.get("budget") else "—"],
        ["Deliver to", mission.get("delivery_location") or "—"],
        ["Deadline", f"{mission.get('deadline_days')} days" if mission.get("deadline_days") else "—"],
        ["Warranty", mission.get("warranty_requirements") or "—"],
    ]
    t = Table(rows, colWidths=[35 * mm, 130 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTE),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
    ]))
    story.append(t)

    if vendors:
        story.append(Paragraph(f"Supplier Shortlist ({len(vendors)})", st["Sec"]))
        vrows = [["#", "Supplier", "Score", "Status", "Reliability"]]
        for i, v in enumerate(vendors):
            vrows.append([str(v.get("rank") or i + 1), (v.get("name") or "")[:38],
                          str(round(v.get("weighted_score") or 0)),
                          v.get("verification_status", ""),
                          str(round(v.get("reliability_score") or 0))])
        vt = Table(vrows, colWidths=[10 * mm, 80 * mm, 20 * mm, 35 * mm, 20 * mm])
        vt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(vt)

    if offers:
        story.append(Paragraph(f"Offers & Landed Cost ({len(offers)})", st["Sec"]))
        orows = [["Supplier", "Unit", "Landed Cost", "Delivery", "Warranty"]]
        for o in offers:
            orows.append([(o.get("vendor_name") or "")[:34],
                          f"{cur} {o.get('negotiated_price')}",
                          f"{cur} {(o.get('total_cost') or 0):,.0f}" if o.get("total_cost") else "—",
                          o.get("delivery_time") or "—", (o.get("warranty") or "—")[:18]])
        ot = Table(orows, colWidths=[55 * mm, 28 * mm, 35 * mm, 25 * mm, 22 * mm])
        ot.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(ot)

    rec = (comparison or {}).get("recommendation")
    if rec:
        story.append(Paragraph("AI Recommendation", st["Sec"]))
        recname = next((o.get("vendor_name") for o in offers
                        if o.get("id") == rec.get("recommended_offer_id")), None)
        if recname:
            story.append(Paragraph(f"<b>Recommended supplier:</b> {recname} "
                                   f"(score {round(rec.get('recommendation_score') or 0)})", st["Body"]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(rec.get("reasoning") or "", st["Body"]))
        for r in (rec.get("risks") or []):
            story.append(Paragraph(f"• Risk: {r}", st["Small"]))

    if approvals:
        story.append(Paragraph("Approval Trail", st["Sec"]))
        for a in approvals:
            story.append(Paragraph(
                f"{a.get('action')} by {a.get('approver_name') or '—'} "
                f"— {a.get('created_at','')[:19].replace('T',' ')}", st["Small"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "Generated by NegoBuy · Figures reflect negotiated/quoted terms and computed landed cost. "
        "Offers marked as preview originate from AI negotiation simulation.", st["Small"]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm, title="NegoBuy Procurement Report")
    doc.build(story)
    buf.seek(0)
    fname = f"NegoBuy-{(mission.get('title') or 'report')[:24].replace(' ', '_')}.pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
