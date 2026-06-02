from unittest.mock import MagicMock, patch

from notifier import TelegramNotifier


def _response(status_code=200, json_data=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    if status_code >= 400:
        response.raise_for_status.side_effect = Exception(f"{status_code} error")
    return response


def test_format_message_escapes_html():
    notifier = TelegramNotifier("token", [], config={"send_delay_seconds": 0})
    message = notifier._format_message(
        {
            "title": "<iPhone & barato>",
            "price": {"amount": "100", "currency_code": "EUR"},
            "description": "Inclui <script>alert(1)</script>",
            "url": "https://example.com/item?a=1&b=2",
            "user": {"login": "seller", "feedback_count": 3, "feedback_reputation": 0.8},
        },
        "Teste <alert>",
    )

    assert "&lt;iPhone &amp; barato&gt;" in message
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message
    assert "<script>" not in message


def test_format_message_includes_resale_costs():
    notifier = TelegramNotifier(
        "token",
        [],
        config={
            "send_delay_seconds": 0,
            "resale": {
                "enabled": True,
                "fixed_shipping_eur": 20,
                "eur_to_kz": 1250,
                "target_currency": "Kz",
            },
        },
    )
    message = notifier._format_message(
        {
            "title": "iPhone",
            "price": {"amount": "90.0", "currency_code": "EUR"},
            "service_fee": {"amount": "5.2", "currency_code": "EUR"},
            "total_item_price": {"amount": "95.2", "currency_code": "EUR"},
            "shipping_fee": {"amount": "3.5", "currency_code": "EUR"},
            "url": "https://example.com/item",
            "user": {"login": "seller", "feedback_count": 3, "feedback_reputation": 1.0},
        },
        "Pesquisa",
    )

    assert "<b>📊 Custo revenda</b>" in message
    assert "💳 <b>Total:</b> 118.70 EUR" in message
    assert "🇦🇴 <b>Total Kz:</b> 148,375 Kz" in message


def test_format_message_highlights_profit_range():
    notifier = TelegramNotifier(
        "token",
        [],
        config={
            "send_delay_seconds": 0,
            "resale": {
                "enabled": True,
                "fixed_shipping_eur": 20,
                "eur_to_kz": 1250,
                "target_currency": "Kz",
                "highlight_profit_min_kz": 40000,
            },
        },
    )
    message = notifier._format_message(
        {
            "title": "iPhone 11",
            "price": {"amount": "90.0", "currency_code": "EUR"},
            "service_fee": {"amount": "5.2", "currency_code": "EUR"},
            "total_item_price": {"amount": "95.2", "currency_code": "EUR"},
            "resale": {"sale_min_kz": 190000, "sale_max_kz": 200000},
            "url": "https://example.com/item",
            "user": {"login": "seller", "feedback_count": 3, "feedback_reputation": 1.0},
        },
        "iPhone 11",
    )

    assert "🚀 <b>BOM LUCRO DETECTADO</b>" in message
    assert "<b>🚀 BOM LUCRO - Revenda</b>" in message
    assert "📈 <b>Venda estimada:</b> 190,000-200,000 Kz" in message
    assert "🔥 <b>Lucro estimado:</b> 46,000-56,000 Kz" in message


@patch("notifier.time.sleep")
@patch("notifier.requests.post")
def test_post_respects_telegram_rate_limit(mock_post, mock_sleep):
    notifier = TelegramNotifier(
        "token",
        [],
        config={
            "send_delay_seconds": 0,
            "send_max_retries": 2,
            "send_retry_backoff_seconds": 1,
        },
    )
    mock_post.side_effect = [
        _response(429, {"parameters": {"retry_after": 4}}),
        _response(200),
    ]

    notifier._post("sendMessage", {"chat_id": "123", "text": "ok"})

    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(4.0)


@patch("notifier.requests.post")
def test_photo_alert_sends_short_photo_caption_then_full_html_message(mock_post):
    notifier = TelegramNotifier("token", [], config={"send_delay_seconds": 0})
    mock_post.return_value = _response(200)

    sent = notifier.send_alert_to_chat(
        {
            "id": 1,
            "title": "iPhone",
            "price": {"amount": "100", "currency_code": "EUR"},
            "description": "Descricao completa",
            "url": "https://example.com/item",
            "photos": [{"url": "https://example.com/photo.jpg"}],
            "user": {"login": "seller", "feedback_count": 3, "feedback_reputation": 1.0},
        },
        "Pesquisa",
        "123",
    )

    assert sent is True
    assert mock_post.call_count == 2
    first_payload = mock_post.call_args_list[0].kwargs["data"]
    second_payload = mock_post.call_args_list[1].kwargs["data"]
    assert "caption" in first_payload
    assert len(first_payload["caption"]) < 1024
    assert second_payload["parse_mode"] == "HTML"
