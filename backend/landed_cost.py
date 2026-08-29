"""True landed-cost engine."""


def compute_landed_cost(offer: dict, quantity: int | None) -> dict:
    """Compute total landed cost. Missing fields are treated as 0 and flagged as assumptions."""
    qty = quantity or offer.get("quantity") or 1
    unit_price = offer.get("negotiated_price") or offer.get("original_price") or 0
    product_price = round(unit_price * qty, 2)

    assumptions = []
    tax = offer.get("taxes")
    if tax is None:
        tax = 0
        assumptions.append("Tax not provided — assumed 0.")
    shipping = offer.get("shipping")
    if shipping is None:
        shipping = 0
        assumptions.append("Shipping not provided — assumed 0.")
    fees = offer.get("fees")
    if fees is None:
        fees = 0
        assumptions.append("Other fees not provided — assumed 0.")

    total = round(product_price + tax + shipping + fees, 2)
    return {
        "product_price": product_price,
        "unit_price": unit_price,
        "quantity": qty,
        "taxes": tax,
        "shipping": shipping,
        "fees": fees,
        "total_cost": total,
        "assumptions": assumptions,
    }
