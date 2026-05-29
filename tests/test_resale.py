from resale import calculate_resale_costs


def test_calculate_resale_costs_with_kz_exchange():
    item = {
        "price": {"amount": "90.0", "currency_code": "EUR"},
        "service_fee": {"amount": "5.2", "currency_code": "EUR"},
        "total_item_price": {"amount": "95.2", "currency_code": "EUR"},
        "shipping_fee": {"amount": "3.5", "currency_code": "EUR"},
    }
    config = {
        "resale": {
            "enabled": True,
            "fixed_shipping_eur": 20,
            "eur_to_kz": 1250,
            "target_currency": "Kz",
        }
    }

    costs = calculate_resale_costs(item, config)

    assert costs["item_price_eur"] == 90.0
    assert costs["vinted_fee_eur"] == 5.2
    assert costs["vinted_shipping_eur"] == 3.5
    assert costs["fixed_shipping_eur"] == 20.0
    assert costs["total_eur"] == 118.7
    assert costs["total_kz"] == 148375.0


def test_calculate_resale_costs_with_profit_range():
    item = {
        "price": {"amount": "90.0", "currency_code": "EUR"},
        "service_fee": {"amount": "5.2", "currency_code": "EUR"},
        "total_item_price": {"amount": "95.2", "currency_code": "EUR"},
        "resale": {"sale_min_kz": 190000, "sale_max_kz": 200000},
    }
    config = {
        "resale": {
            "enabled": True,
            "fixed_shipping_eur": 20,
            "eur_to_kz": 1250,
            "target_currency": "Kz",
            "highlight_profit_min_kz": 40000,
        }
    }

    costs = calculate_resale_costs(item, config)

    assert costs["total_kz"] == 144000.0
    assert costs["profit_min_kz"] == 46000.0
    assert costs["profit_max_kz"] == 56000.0
    assert costs["is_high_profit"] is True
