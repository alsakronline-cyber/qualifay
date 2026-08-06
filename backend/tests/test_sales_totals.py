"""Money math for sales documents — the numbers a customer sees must be exact, so the pure
totals function is unit-tested across line discounts, document discounts, VAT, and rounding."""
from app.api.sales import compute_totals

LINES = [
    {"description": "Widget", "quantity": 2, "unit_price": 100, "discount_pct": 0},   # 200
    {"description": "Gadget", "quantity": 1, "unit_price": 50, "discount_pct": 10},    # 45
]


def test_line_totals_and_vat():
    t = compute_totals(LINES, "amount", 0, 14.0)
    assert t["lines"][0]["line_total"] == 200.0
    assert t["lines"][1]["line_total"] == 45.0
    assert t["subtotal"] == 245.0
    assert t["discount_total"] == 0.0
    assert t["tax_total"] == 34.30          # 245 * 14%
    assert t["grand_total"] == 279.30


def test_document_percent_discount():
    t = compute_totals(LINES, "percent", 10, 14.0)
    assert t["discount_total"] == 24.50     # 10% of 245
    taxable = 245.0 - 24.50
    assert t["tax_total"] == round(taxable * 0.14, 2)
    assert t["grand_total"] == round(taxable * 1.14, 2)


def test_document_amount_discount():
    t = compute_totals(LINES, "amount", 45, 14.0)
    assert t["discount_total"] == 45.0
    assert t["tax_total"] == 28.0           # (245-45) * 14%
    assert t["grand_total"] == 228.0


def test_discount_cannot_exceed_subtotal():
    t = compute_totals(LINES, "amount", 9999, 14.0)
    assert t["discount_total"] == 245.0     # clamped
    assert t["grand_total"] == 0.0


def test_zero_vat_and_empty():
    assert compute_totals(LINES, "amount", 0, 0)["tax_total"] == 0.0
    empty = compute_totals([], "amount", 0, 14.0)
    assert empty["subtotal"] == 0.0 and empty["grand_total"] == 0.0
