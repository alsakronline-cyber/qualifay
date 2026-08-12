"""Sales documents API — Inquiry → Quotation → Sales Order → Invoice.

One model (SalesDoc + SalesDocLine) backs all four types; totals are computed server-side so
the numbers can never drift from the lines. `convert` creates the next document in the flow,
copying the lines. Everything is tenant-scoped.
"""
import html as _html
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.models import SalesDoc, SalesDocLine, SalesDocType, SalesDocStatus, Tenant, Lead

router = APIRouter()

_PREFIX = {"inquiry": "INQ", "quotation": "QUO", "sales_order": "SO", "invoice": "INV"}
# Which type a document can convert into (the standard sales flow, forward-only).
_CONVERT_NEXT = {"inquiry": "quotation", "quotation": "sales_order", "sales_order": "invoice"}


# ── pure totals (unit-tested) ───────────────────────────────────────────────
def compute_totals(lines: list, discount_type: str, discount_value: float, tax_rate: float) -> dict:
    """Line total = qty × unit_price × (1 − line_discount%). Document discount applies to the
    subtotal, tax (Egyptian VAT) applies to the discounted subtotal. All rounded to 2 dp."""
    subtotal = 0.0
    norm = []
    for ln in lines:
        qty = float(ln.get("quantity") or 0)
        price = float(ln.get("unit_price") or 0)
        disc = float(ln.get("discount_pct") or 0)
        lt = round(qty * price * (1 - disc / 100.0), 2)
        subtotal += lt
        norm.append({**ln, "line_total": lt})
    subtotal = round(subtotal, 2)
    if (discount_type or "amount") == "percent":
        discount_total = round(subtotal * float(discount_value or 0) / 100.0, 2)
    else:
        discount_total = round(float(discount_value or 0), 2)
    discount_total = max(0.0, min(discount_total, subtotal))
    taxable = round(subtotal - discount_total, 2)
    tax_total = round(taxable * float(tax_rate or 0) / 100.0, 2)
    grand = round(taxable + tax_total, 2)
    return {"subtotal": subtotal, "discount_total": discount_total,
            "tax_total": tax_total, "grand_total": grand, "lines": norm}


async def _next_number(db, tenant_id: str, doc_type: str) -> str:
    prefix = _PREFIX.get(doc_type, "DOC")
    year = datetime.utcnow().year
    n = (await db.execute(select(func.count(SalesDoc.id)).where(
        SalesDoc.tenant_id == tenant_id, SalesDoc.doc_type == SalesDocType(doc_type)))).scalar() or 0
    return f"{prefix}-{year}-{n + 1:04d}"


def _parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


# ── schemas ─────────────────────────────────────────────────────────────────
class LineIn(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    discount_pct: float = 0.0


class DocIn(BaseModel):
    doc_type: str = "quotation"
    status: Optional[str] = None
    lead_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_company: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_address: Optional[str] = None
    customer_tax_id: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: str = "EGP"
    discount_type: str = "amount"
    discount_value: float = 0.0
    tax_rate: float = 14.0
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    lines: List[LineIn] = Field(default_factory=list)


def _line_dict(ln: SalesDocLine) -> dict:
    return {"id": ln.id, "position": ln.position, "description": ln.description,
            "quantity": ln.quantity, "unit_price": ln.unit_price,
            "discount_pct": ln.discount_pct, "line_total": ln.line_total}


def _doc_dict(d: SalesDoc) -> dict:
    return {
        "id": d.id, "doc_type": d.doc_type.value if d.doc_type else None,
        "number": d.number, "status": d.status.value if d.status else None,
        "lead_id": d.lead_id,
        "customer_name": d.customer_name, "customer_company": d.customer_company,
        "customer_email": d.customer_email, "customer_phone": d.customer_phone,
        "customer_address": d.customer_address, "customer_tax_id": d.customer_tax_id,
        "issue_date": d.issue_date.isoformat() if d.issue_date else None,
        "due_date": d.due_date.isoformat() if d.due_date else None,
        "currency": d.currency, "discount_type": d.discount_type, "discount_value": d.discount_value,
        "tax_rate": d.tax_rate, "subtotal": d.subtotal, "discount_total": d.discount_total,
        "tax_total": d.tax_total, "grand_total": d.grand_total,
        "payment_terms": d.payment_terms, "notes": d.notes, "terms": d.terms,
        "converted_from_id": d.converted_from_id,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "lines": [_line_dict(ln) for ln in sorted(d.lines, key=lambda x: x.position or 0)],
    }


async def _seller(db, tenant_id: str) -> dict:
    """Seller header pulled from the tenant's onboarding profile — makes documents on-brand."""
    t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    p = (t.tenant_profile or {}) if t else {}
    return {"name": p.get("business_name") or (t.name if t else ""),
            "industry": p.get("industry", ""), "website": p.get("website", ""),
            "tax_id": p.get("tax_id", ""), "address": p.get("address", ""),
            "phone": p.get("phone", ""), "email": p.get("email", ""),
            "logo": p.get("logo", "")}


def _apply(doc: SalesDoc, body: DocIn):
    """Write scalar fields + recompute money from the lines onto a doc (create or update)."""
    doc.customer_name = body.customer_name
    doc.customer_company = body.customer_company
    doc.customer_email = body.customer_email
    doc.customer_phone = body.customer_phone
    doc.customer_address = body.customer_address
    doc.customer_tax_id = body.customer_tax_id
    doc.lead_id = body.lead_id
    doc.currency = body.currency or "EGP"
    doc.discount_type = body.discount_type or "amount"
    doc.discount_value = float(body.discount_value or 0)
    doc.tax_rate = float(body.tax_rate if body.tax_rate is not None else 14.0)
    doc.payment_terms = body.payment_terms
    doc.notes = body.notes
    doc.terms = body.terms
    if body.issue_date:
        doc.issue_date = _parse_dt(body.issue_date) or doc.issue_date
    doc.due_date = _parse_dt(body.due_date)
    if body.status in [s.value for s in SalesDocStatus]:
        doc.status = SalesDocStatus(body.status)

    totals = compute_totals([ln.dict() for ln in body.lines],
                            doc.discount_type, doc.discount_value, doc.tax_rate)
    doc.subtotal = totals["subtotal"]
    doc.discount_total = totals["discount_total"]
    doc.tax_total = totals["tax_total"]
    doc.grand_total = totals["grand_total"]
    doc.lines = [SalesDocLine(
        position=i, description=ln["description"], quantity=float(ln.get("quantity") or 0),
        unit_price=float(ln.get("unit_price") or 0), discount_pct=float(ln.get("discount_pct") or 0),
        line_total=ln["line_total"]) for i, ln in enumerate(totals["lines"])]


# ── endpoints ───────────────────────────────────────────────────────────────
_ITEM_HEADERS = {"description", "الوصف", "item", "البند", "صنف", "اسم الصنف", "بيان"}


def _rows_to_items(rows: list) -> list:
    """Map spreadsheet/CSV rows -> line items. Columns: description, quantity, unit_price,
    discount%. A 2-column row is read as (description, unit_price)."""
    def num(v):
        try:
            return float(str(v).replace(",", "").replace("%", "").strip())
        except (ValueError, TypeError):
            return 0.0
    out = []
    for r in rows:
        cells = [("" if c is None else str(c)).strip() for c in (r or [])]
        while cells and cells[-1] == "":
            cells.pop()
        if not cells or not cells[0]:
            continue
        desc = cells[0]
        if desc.lower() in _ITEM_HEADERS:
            continue
        if len(cells) >= 3:
            qty, price, disc = (num(cells[1]) or 1.0), num(cells[2]), num(cells[3]) if len(cells) > 3 else 0.0
        elif len(cells) == 2:
            qty, price, disc = 1.0, num(cells[1]), 0.0
        else:
            qty, price, disc = 1.0, 0.0, 0.0
        out.append({"description": desc[:500], "quantity": qty, "unit_price": price, "discount_pct": disc})
    return out[:500]


@router.post("/parse-items", summary="Parse an uploaded CSV/Excel item list into line items")
async def parse_items(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    name = (file.filename or "").lower()
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="الملف كبير جداً (الحد 5 ميجابايت)")
    rows = []
    try:
        if name.endswith((".xlsx", ".xlsm")):
            import io
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            for row in wb.active.iter_rows(values_only=True):
                rows.append(list(row))
        else:
            import csv
            import io as _io
            text = content.decode("utf-8-sig", errors="ignore")
            rows = list(csv.reader(_io.StringIO(text)))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"تعذّر قراءة الملف: {e}")
    return {"items": _rows_to_items(rows)}


@router.get("", summary="List sales documents")
@router.get("/", include_in_schema=False)
async def list_docs(doc_type: Optional[str] = None, status: Optional[str] = None,
                    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q = select(SalesDoc).where(SalesDoc.tenant_id == current_user["tenant_id"])
    if doc_type:
        q = q.where(SalesDoc.doc_type == SalesDocType(doc_type))
    if status:
        q = q.where(SalesDoc.status == SalesDocStatus(status))
    q = q.options(selectinload(SalesDoc.lines)).order_by(SalesDoc.created_at.desc()).limit(500)
    docs = (await db.execute(q)).scalars().all()
    return [_doc_dict(d) for d in docs]


async def _load(db, tenant_id, doc_id) -> SalesDoc:
    d = (await db.execute(select(SalesDoc).where(and_(
        SalesDoc.id == doc_id, SalesDoc.tenant_id == tenant_id)).options(
        selectinload(SalesDoc.lines)))).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    return d


@router.post("", summary="Create a sales document")
async def create_doc(body: DocIn, current_user=Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    if body.doc_type not in _PREFIX:
        raise HTTPException(status_code=400, detail=f"doc_type must be one of {list(_PREFIX)}")
    tid = current_user["tenant_id"]
    doc = SalesDoc(tenant_id=tid, doc_type=SalesDocType(body.doc_type),
                   number=await _next_number(db, tid, body.doc_type),
                   status=SalesDocStatus.draft)
    _apply(doc, body)
    db.add(doc)
    await db.commit()
    await db.refresh(doc, ["lines"])
    return _doc_dict(doc)


@router.get("/{doc_id}", summary="Get one document (with seller header for printing)")
async def get_doc(doc_id: str, current_user=Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    d = await _load(db, current_user["tenant_id"], doc_id)
    return {**_doc_dict(d), "seller": await _seller(db, current_user["tenant_id"])}


@router.put("/{doc_id}", summary="Update / edit a document")
async def update_doc(doc_id: str, body: DocIn, current_user=Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    d = await _load(db, current_user["tenant_id"], doc_id)
    _apply(d, body)
    await db.commit()
    await db.refresh(d, ["lines"])
    return _doc_dict(d)


@router.delete("/{doc_id}", summary="Delete a document")
async def delete_doc(doc_id: str, current_user=Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    d = await _load(db, current_user["tenant_id"], doc_id)
    await db.delete(d)
    await db.commit()
    return {"deleted": True, "id": doc_id}


_PDF_TITLE = {"inquiry": ("INQUIRY", "طلب عرض سعر"), "quotation": ("QUOTATION", "عرض سعر"),
              "sales_order": ("SALES ORDER", "أمر بيع"), "invoice": ("INVOICE", "فاتورة")}


def _pdf_html(d: SalesDoc, seller: dict) -> str:
    """Self-contained professional A4 HTML rendered to PDF by Chromium (mirrors /doc-print)."""
    e = _html.escape
    cur = d.currency or "EGP"
    money = lambda n: f"{(n or 0):,.2f} {cur}"
    dt = lambda x: x.strftime("%d/%m/%Y") if x else "—"
    en, ar = _PDF_TITLE.get(d.doc_type.value, ("DOCUMENT", "مستند"))
    logo = seller.get("logo") or ""
    logo_html = (f'<img src="{logo}" style="max-height:64px;max-width:220px;margin-bottom:8px" />'
                 if logo.startswith("data:image/") else "")
    due_label = {"quotation": "Valid Until", "invoice": "Due Date"}.get(d.doc_type.value, "Required Date")

    seller_lines = "".join(f"<div>{e(v)}</div>" for v in [
        seller.get("address"), " · ".join([x for x in [seller.get("phone"), seller.get("email")] if x]),
        seller.get("website"), (f"Tax ID: {seller.get('tax_id')}" if seller.get("tax_id") else "")] if v)
    cust_lines = "".join(f"<div>{e(v)}</div>" for v in [
        (d.customer_name if d.customer_company and d.customer_name else ""),
        d.customer_address, " · ".join([x for x in [d.customer_phone, d.customer_email] if x]),
        (f"Tax ID: {d.customer_tax_id}" if d.customer_tax_id else "")] if v)
    rows = "".join(
        f"<tr><td>{e(ln.description or '')}</td><td class='r'>{ln.quantity:g}</td>"
        f"<td class='r'>{money(ln.unit_price)}</td>"
        f"<td class='r'>{(str(ln.discount_pct)+'%') if ln.discount_pct else '—'}</td>"
        f"<td class='r'>{money(ln.line_total)}</td></tr>"
        for ln in sorted(d.lines, key=lambda x: x.position or 0))
    disc_row = (f"<tr><td class='muted'>Discount</td><td class='r'>− {money(d.discount_total)}</td></tr>"
                if (d.discount_total or 0) > 0 else "")
    pay = (f"<div style='margin-bottom:10px'><div class='muted' style='font-weight:700'>Payment Terms</div>"
           f"<div style='font-size:13px;white-space:pre-wrap'>{e(d.payment_terms)}</div></div>") if d.payment_terms else ""
    notes = (f"<div style='margin-bottom:10px'><div class='muted' style='font-weight:700'>Notes</div>"
             f"<div style='font-size:13px;white-space:pre-wrap'>{e(d.notes)}</div></div>") if d.notes else ""
    terms = (f"<div><div class='muted' style='font-weight:700'>Terms &amp; Conditions</div>"
             f"<div style='font-size:12px;white-space:pre-wrap;color:#374151'>{e(d.terms)}</div></div>") if d.terms else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      * {{ font-family:'Noto Sans Arabic','Noto Sans','Segoe UI',sans-serif; }}
      body {{ color:#111827; margin:0; padding:24px; }}
      .row {{ display:flex; justify-content:space-between; align-items:flex-start; gap:24px; }}
      .muted {{ color:#6b7280; font-size:12px; line-height:1.6; }}
      table {{ width:100%; border-collapse:collapse; margin-top:10px; }}
      th {{ background:#111827; color:#fff; font-size:12px; padding:9px 10px; text-align:left; }}
      th.r,td.r {{ text-align:right; }}
      td {{ padding:9px 10px; border-bottom:1px solid #e5e7eb; font-size:13px; }}
      .tot td {{ border:none; padding:4px 10px; }}
    </style></head><body>
      <div class="row" style="border-bottom:2px solid #111827;padding-bottom:16px">
        <div>{logo_html}
          <div style="font-size:22px;font-weight:800">{e(seller.get('name') or '—')}</div>
          <div class="muted" style="margin-top:4px">{seller_lines}</div></div>
        <div style="text-align:right"><div style="font-size:26px;font-weight:800;letter-spacing:1px">{en}</div>
          <div style="font-size:15px">{ar}</div>
          <div class="muted" style="margin-top:8px"><div><b>No:</b> {e(d.number)}</div>
          <div><b>Date:</b> {dt(d.issue_date)}</div>
          {f'<div><b>{due_label}:</b> {dt(d.due_date)}</div>' if d.due_date else ''}</div></div>
      </div>
      <div style="margin-top:20px"><div class="muted" style="font-weight:700">BILL TO</div>
        <div style="font-weight:700;font-size:15px">{e(d.customer_company or d.customer_name or '—')}</div>
        <div class="muted">{cust_lines}</div></div>
      <table><thead><tr><th style="width:48%">Description</th><th class="r">Qty</th>
        <th class="r">Unit Price</th><th class="r">Disc%</th><th class="r">Amount</th></tr></thead>
        <tbody>{rows}</tbody></table>
      <div style="display:flex;justify-content:flex-end;margin-top:12px">
        <table style="width:300px" class="tot"><tbody>
          <tr><td class="muted">Subtotal</td><td class="r">{money(d.subtotal)}</td></tr>
          {disc_row}
          <tr><td class="muted">VAT ({d.tax_rate:g}%)</td><td class="r">{money(d.tax_total)}</td></tr>
          <tr style="border-top:2px solid #111827"><td style="font-weight:800;font-size:15px;padding-top:8px">TOTAL</td>
            <td class="r" style="font-weight:800;font-size:15px;padding-top:8px">{money(d.grand_total)}</td></tr>
        </tbody></table></div>
      <div style="margin-top:28px;border-top:1px solid #e5e7eb;padding-top:16px">{pay}{notes}{terms}</div>
      <div style="text-align:center;margin-top:36px;font-size:11px;color:#9ca3af">Generated by Qualifay · {e(d.number)}</div>
    </body></html>"""


async def _html_to_pdf(html_str: str) -> bytes:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            await page.set_content(html_str, wait_until="networkidle")
            return await page.pdf(format="A4", print_background=True,
                                  margin={"top": "10mm", "bottom": "10mm", "left": "8mm", "right": "8mm"})
        finally:
            await browser.close()


@router.get("/{doc_id}/pdf", summary="Download the document as a PDF")
async def doc_pdf(doc_id: str, current_user=Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    tid = current_user["tenant_id"]
    d = await _load(db, tid, doc_id)
    seller = await _seller(db, tid)
    try:
        pdf = await _html_to_pdf(_pdf_html(d, seller))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{d.number}.pdf"'})


@router.post("/{doc_id}/convert", summary="Convert to the next document in the flow")
async def convert_doc(doc_id: str, current_user=Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    tid = current_user["tenant_id"]
    src = await _load(db, tid, doc_id)
    nxt = _CONVERT_NEXT.get(src.doc_type.value)
    if not nxt:
        raise HTTPException(status_code=400, detail="This document type cannot be converted further")
    doc = SalesDoc(
        tenant_id=tid, doc_type=SalesDocType(nxt), number=await _next_number(db, tid, nxt),
        status=SalesDocStatus.draft, converted_from_id=src.id,
        lead_id=src.lead_id, customer_name=src.customer_name, customer_company=src.customer_company,
        customer_email=src.customer_email, customer_phone=src.customer_phone,
        customer_address=src.customer_address, customer_tax_id=src.customer_tax_id,
        currency=src.currency, discount_type=src.discount_type, discount_value=src.discount_value,
        tax_rate=src.tax_rate, subtotal=src.subtotal, discount_total=src.discount_total,
        tax_total=src.tax_total, grand_total=src.grand_total,
        payment_terms=src.payment_terms, terms=src.terms,
    )
    doc.lines = [SalesDocLine(
        position=ln.position, description=ln.description, quantity=ln.quantity,
        unit_price=ln.unit_price, discount_pct=ln.discount_pct, line_total=ln.line_total)
        for ln in src.lines]
    db.add(doc)
    await db.commit()
    await db.refresh(doc, ["lines"])
    return _doc_dict(doc)
