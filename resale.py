def parse_money(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, dict):
        value = value.get("amount", value.get("numeric", default))
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def get_first_money(item: dict, keys: list, default=0.0):
    for key in keys:
        if key in item and item.get(key) is not None:
            return parse_money(item.get(key), default=default)
    return default


def calculate_resale_costs(item: dict, config: dict) -> dict:
    resale_config = config.get("resale", {})
    enabled = resale_config.get("enabled", False)
    resale_profile = item.get("resale", {})

    item_price = get_first_money(item, ["price", "price_numeric"])
    vinted_fee = get_first_money(item, ["service_fee", "buyer_protection_fee"])
    total_item_price = get_first_money(item, ["total_item_price"], default=item_price + vinted_fee)
    item_shipping = get_first_money(
        item,
        ["shipping_fee", "shipment_price", "shipping_price", "domestic_shipping_fee"],
    )

    fixed_shipping = parse_money(resale_config.get("fixed_shipping_eur", 0))
    eur_to_kz = parse_money(resale_config.get("eur_to_kz", 1), default=1)
    target_profit_min_kz = parse_money(resale_config.get("highlight_profit_min_kz", 0))

    total_eur = total_item_price + item_shipping + fixed_shipping
    total_kz = total_eur * eur_to_kz
    sale_min_kz = parse_money(resale_profile.get("sale_min_kz"), default=None)
    sale_max_kz = parse_money(resale_profile.get("sale_max_kz"), default=None)
    profit_min_kz = sale_min_kz - total_kz if sale_min_kz is not None else None
    profit_max_kz = sale_max_kz - total_kz if sale_max_kz is not None else None
    margin_min_percent = (profit_min_kz / total_kz * 100) if profit_min_kz is not None and total_kz else None
    margin_max_percent = (profit_max_kz / total_kz * 100) if profit_max_kz is not None and total_kz else None

    return {
        "enabled": enabled,
        "currency": resale_config.get("target_currency", "Kz"),
        "eur_to_kz": eur_to_kz,
        "item_price_eur": item_price,
        "vinted_fee_eur": vinted_fee,
        "vinted_shipping_eur": item_shipping,
        "fixed_shipping_eur": fixed_shipping,
        "total_eur": total_eur,
        "total_kz": total_kz,
        "sale_min_kz": sale_min_kz,
        "sale_max_kz": sale_max_kz,
        "profit_min_kz": profit_min_kz,
        "profit_max_kz": profit_max_kz,
        "margin_min_percent": margin_min_percent,
        "margin_max_percent": margin_max_percent,
        "is_high_profit": profit_min_kz is not None and profit_min_kz >= target_profit_min_kz,
    }
