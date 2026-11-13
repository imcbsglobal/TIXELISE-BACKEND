"""Tax resolution and per-line arithmetic for ticket sales.

Contract
--------
* The taxable amount of a sale is the price the administrator configured
  ``EventPrice.amount``; it is reported unchanged as ``Sale.gross_total``.
* Tax is computed **per sale line** and rounded to two decimals with
  ``ROUND_HALF_UP``. Lines are summed afterwards, so
  ``Sale.tax_total == sum(SaleItem.tax_amount)`` always holds and the printed
  total is exactly the sum of its parts.
* ``total_payable = gross_total + tax_total - refund_total``. With tax disabled
  every new field is zero and every total equals the pre-tax figure, which is
  why existing reports and rows are unaffected.
* The rate comes from the stored ``TaxSetting`` copy, never from the central
  master: nothing here performs network I/O, so a sale can never block on (or
  fail because of) a third-party host.
* Comp (``source=manual``) tickets are never taxed.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .models import TaxSetting

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
ZERO = Decimal("0.00")


def _to_rate(value) -> Decimal:
    """One percentage from the master, clamped to 0-100 and normalised to 2dp."""
    if value in (None, ""):
        return ZERO
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return ZERO
    if not number.is_finite() or number < 0 or number > HUNDRED:
        return ZERO
    return number.quantize(CENT, rounding=ROUND_HALF_UP)


def rate_from_master_row(kind, row) -> Decimal:
    """The single rate Tixelise charges for one central tax-master record.

    India exposes four components (``cgst``/``sgst``/``igst``/``gst``) and real
    rows on the master already disagree with each other (e.g. ``igst: "0.00"``
    beside ``gst: "18.00"``), so the total ``gst`` is used and the components are
    kept for display only. ``other`` has one flat ``tax`` rate.
    """
    record = row if isinstance(row, dict) else {}
    field = "gst" if str(kind) == TaxSetting.Kind.INDIA else "tax"
    return _to_rate(record.get(field))


def resolve_tax(tenant):
    """The company ``TaxSetting`` to charge, or ``None`` when tax is off.

    A zero rate is treated as "no tax": charging 0% is indistinguishable from
    switching the feature off, and returning ``None`` keeps the sale path
    identical to the pre-tax code.
    """
    setting = TaxSetting.objects.filter(tenant=tenant).first()
    if setting is None or not setting.enabled or setting.rate <= ZERO:
        return None
    return setting


@dataclass(frozen=True)
class ResolvedTax:
    """The rate, label and HSN a sale line should freeze."""

    rate: Decimal
    code: str
    name: str
    prices_include_tax: bool
    hsn_code: str = ""


def resolve_tax_for_event(event, tenant):
    """Resolve the tax an event's ticket sales should charge.

    An event can charge its own rate, explicitly opt out, or inherit the
    company-wide setting. ``None`` means no tax, exactly like ``resolve_tax``.
    """
    mode = getattr(event, "tax_mode", None)
    if mode == "disabled":
        return None
    if mode == "event":
        rate = _to_rate(getattr(event, "tax_rate", None))
        if rate <= ZERO:
            return None
        return ResolvedTax(
            rate=rate,
            code="",
            name="Event tax",
            prices_include_tax=bool(event.prices_include_tax),
            hsn_code=str(event.hsn_code or "").strip(),
        )

    setting = resolve_tax(tenant)
    if setting is None:
        return None
    return ResolvedTax(
        rate=setting.rate,
        code=setting.code,
        name=setting.name,
        prices_include_tax=setting.prices_include_tax,
        hsn_code="",
    )


def apply_tax_to_line(*, unit_price, quantity, tax):
    """``(taxable_line_total, tax_amount)`` for one sale line.

    Exclusive (the default) adds tax on top of the configured price. Inclusive
    extracts the tax the price already contains, so ``line_total`` stays the
    taxable base and ``line_total + tax_amount`` is what the customer pays.
    """
    gross = unit_price * quantity
    if tax is None:
        return gross, ZERO

    if tax.prices_include_tax:
        divisor = Decimal("1") + (tax.rate / HUNDRED)
        tax_amount = (gross - (gross / divisor)).quantize(CENT, rounding=ROUND_HALF_UP)
        return (gross - tax_amount).quantize(CENT, rounding=ROUND_HALF_UP), tax_amount

    tax_amount = (gross * tax.rate / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
    return gross, tax_amount


def tax_snapshot_fields(tax) -> dict:
    """The four frozen fields written onto every ``SaleItem``."""
    if tax is None:
        return {
            "tax_rate_snapshot": ZERO,
            "tax_code": "",
            "tax_name": "",
            "tax_amount": ZERO,
            "hsn_code": "",
        }
    return {
        "tax_rate_snapshot": tax.rate,
        "tax_code": tax.code,
        "tax_name": tax.name,
        "hsn_code": getattr(tax, "hsn_code", ""),
    }
