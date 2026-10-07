from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def extract_vat(gross, rate):
    if not Decimal("0") <= rate <= Decimal("100"):
        raise ValueError("VAT percentage must be between 0 and 100.")
    net = money(gross / (Decimal("1") + rate / Decimal("100")))
    return net, gross - net


def allocate_discount(discount, amounts):
    """Largest remainder allocation in cents, stable in order-item order."""
    total = sum(amounts, Decimal("0"))
    if discount < 0 or discount > total:
        raise ValueError("Discount must be between zero and the merchandise subtotal.")
    if not total:
        return [Decimal("0.00") for _ in amounts]
    exact = [discount * amount / total / CENT for amount in amounts]
    cents = [int(value) for value in exact]
    remaining = int(discount / CENT) - sum(cents)
    priority = sorted(range(len(amounts)), key=lambda index: exact[index] - cents[index], reverse=True)
    for index in priority[:remaining]:
        cents[index] += 1
    return [value * CENT for value in cents]


def vat_summary(invoice):
    groups = {}
    for item in invoice.items.all():
        row = groups.setdefault(
            item.vat_rate,
            {"rate": item.vat_rate, "net": Decimal("0.00"), "vat": Decimal("0.00"), "gross": Decimal("0.00")},
        )
        row["net"] += item.line_total_ex_vat
        row["vat"] += item.vat_amount
        row["gross"] += item.line_total_inc_vat
    return [groups[rate] for rate in sorted(groups)]
