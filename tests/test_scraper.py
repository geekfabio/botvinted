import pytest
import requests
import time
from unittest.mock import patch, MagicMock
from scraper import VintedScraper


def _catalog_item(item_id, title, price, status="Muito bom"):
    return (
        f'<div data-testid="product-item-id-{item_id}" class="item">'
        f'<img data-testid="product-item-id-{item_id}--image--img" src="https://images.example/{item_id}.jpg">'
        f'<a data-testid="product-item-id-{item_id}--overlay-link" '
        f'href="/items/{item_id}-listing" title="{title}"></a>'
        f'<p data-testid="product-item-id-{item_id}--description-title">{title}</p>'
        f'<p data-testid="product-item-id-{item_id}--description-subtitle">{status}</p>'
        f'<p data-testid="product-item-id-{item_id}--price-text">{price}</p>'
        "</div>"
    )


@patch("scraper.requests.Session")
def test_vinted_scraper_initialization(mock_session):
    # Setup mock
    mock_instance = MagicMock()
    mock_session.return_value = mock_instance
    
    # Previne que o fetch_new_cookies faça pedidos reais
    with patch.object(VintedScraper, '_fetch_new_cookies') as mock_fetch:
        with patch.object(VintedScraper, '_load_or_fetch_cookies') as mock_load:
            config = {"country": "es"}
            scraper = VintedScraper(config)
            
            assert scraper.country == "es"
            assert scraper.domain == "vinted.es"
            assert scraper.base_url == "https://www.vinted.es"
            assert scraper.catalog_url == "https://www.vinted.es/catalog"
            assert "/api/" not in scraper.catalog_url

@patch("scraper.requests.Session")
def test_scraper_search_pagination(mock_session):
    config = {"country": "pt", "delay_between_requests": 0, "results_per_page": 2}
    
    with patch.object(VintedScraper, '_load_or_fetch_cookies'):
        scraper = VintedScraper(config)
        
        # Mock the session.get response
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 200
        mock_response_1.text = _catalog_item(1, "iPhone 12", "105,00 €") + _catalog_item(2, "iPhone 13", "200,00 €")
        
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.text = _catalog_item(3, "iPhone 14", "300,00 €") # Menos que per_page -> deve parar
        
        scraper.session.get.side_effect = [mock_response_1, mock_response_2]
        
        params = {"search_text": "test", "per_page": 2}
        items = scraper.search(params, max_pages=3)
        
        # Devem ter sido retornados 3 itens no total
        assert [item["id"] for item in items] == ["1", "2", "3"]
        assert items[0]["price"] == {"amount": "105.00", "currency_code": "EUR"}
        assert items[0]["photos"] == [{"url": "https://images.example/1.jpg"}]
        assert items[0]["status"] == "Muito bom"
        # O scraper deve ter feito 2 requests, embora o max_pages fosse 3 (porque a página 2 retornou poucos resultados)
        assert scraper.session.get.call_count == 2

@patch("scraper.time.sleep")
@patch("scraper.requests.Session")
def test_scraper_retries_after_rate_limit(mock_session, mock_sleep):
    config = {
        "country": "pt",
        "delay_between_requests": 0,
        "retry_max_attempts": 2,
        "retry_backoff_seconds": 1,
        "retry_jitter_seconds": 0,
    }

    with patch.object(VintedScraper, '_load_or_fetch_cookies'):
        scraper = VintedScraper(config)

        mock_rate_limit = MagicMock()
        mock_rate_limit.status_code = 429
        mock_rate_limit.headers = {"Retry-After": "3"}

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.headers = {}
        mock_success.text = _catalog_item(1, "iPhone", "100,00 €")

        scraper.session.get.side_effect = [mock_rate_limit, mock_success]

        items = scraper.search({"search_text": "test", "per_page": 2}, max_pages=1)

        assert items[0]["id"] == "1"
        assert items[0]["title"] == "iPhone"
        assert scraper.session.get.call_count == 2
        mock_sleep.assert_called_once_with(3.0)

@patch("scraper.requests.Session")
@patch("scraper.time.sleep")
def test_retry_after_is_capped_by_config(mock_sleep, mock_session):
    config = {
        "country": "pt",
        "delay_between_requests": 0,
        "retry_max_attempts": 2,
        "retry_backoff_seconds": 1,
        "retry_jitter_seconds": 0,
        "retry_after_max_seconds": 2,
    }

    with patch.object(VintedScraper, '_load_or_fetch_cookies'):
        scraper = VintedScraper(config)

        mock_rate_limit = MagicMock()
        mock_rate_limit.status_code = 429
        mock_rate_limit.headers = {"Retry-After": "10"}

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.headers = {}
        mock_success.text = _catalog_item(1, "iPhone", "100,00 €")

        scraper.session.get.side_effect = [mock_rate_limit, mock_success]

        items = scraper.search({"search_text": "test", "per_page": 2}, max_pages=1)

        assert items[0]["id"] == "1"
        assert scraper.session.get.call_count == 2
        mock_sleep.assert_called_once_with(2.0)

@patch("scraper.requests.Session")
def test_get_item_details_enriches_description_and_seller_feedback(mock_session):
    html = (
        '<meta name="description" content="iPhone usado em bom estado"/>'
        '\\"feedback_count\\":4,\\"feedback_reputation\\":0.8,'
        '\\"item_id\\":\\"1\\",\\"name\\":\\"seller_current\\"'
    )

    with patch.object(VintedScraper, '_load_or_fetch_cookies'):
        scraper = VintedScraper({"country": "pt"})

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        scraper.session.get.return_value = mock_response

        item = {
            "id": 1,
            "url": "https://www.vinted.pt/items/1-test",
            "user": {"login": "seller"},
            "search_tracking_params": {"score": 2000000000},
        }

        enriched = scraper.get_item_details(item)

        assert enriched["description"] == "iPhone usado em bom estado"
        assert enriched["user"]["feedback_count"] == 4
        assert enriched["user"]["feedback_reputation"] == 0.8
        assert enriched["user"]["login"] == "seller_current"
        assert enriched["detail_loaded"] is True


@patch("scraper.requests.Session")
def test_search_url_encodes_query_and_preserves_input_params(mock_session):
    with patch.object(VintedScraper, "_load_or_fetch_cookies"):
        scraper = VintedScraper({"country": "pt", "delay_between_requests": 0})
        response = MagicMock()
        response.status_code = 200
        response.text = _catalog_item(7, "iPhone & case", "1.234,50 €")
        scraper.session.get.return_value = response

        params = {"search_text": "iphone & case", "per_page": 1, "status_ids[]": [2, 3]}
        items = scraper.search(params, max_pages=1)

        assert items[0]["price"]["amount"] == "1234.50"
        assert params == {"search_text": "iphone & case", "per_page": 1, "status_ids[]": [2, 3]}
        requested_url = scraper.session.get.call_args.args[0]
        assert "search_text=iphone+%26+case" in requested_url
        assert "status_ids%5B%5D=2&status_ids%5B%5D=3" in requested_url


@patch("scraper.requests.Session")
def test_created_timestamp_reads_current_relative_upload_date(mock_session):
    with patch.object(VintedScraper, "_load_or_fetch_cookies"):
        scraper = VintedScraper({"country": "pt"})
        html = r'\"code\":\"upload_date\",\"data\":{\"title\":\"Carregado\",\"value\":\"há 3 minutos\"}'

        timestamp = scraper._extract_created_timestamp({}, html)

        assert timestamp is not None
        assert 0 <= time.time() - timestamp < 5 * 60


@patch("scraper.requests.Session")
def test_get_item_details_marks_deleted_items_unavailable(mock_session):
    with patch.object(VintedScraper, '_load_or_fetch_cookies'):
        scraper = VintedScraper({"country": "pt"})

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError(response=mock_response)
        scraper.session.get.return_value = mock_response

        item = {
            "id": 1,
            "url": "https://www.vinted.pt/items/1-deleted",
        }

        enriched = scraper.get_item_details(item)

        assert enriched["detail_loaded"] is False
        assert enriched["unavailable"] is True
        assert enriched["detail_error_status"] == 404


@patch("scraper.os.remove")
@patch("scraper.os.path.exists")
@patch("scraper.requests.Session")
def test_fetch_new_cookies_clears_stale_cookie_state(mock_session, mock_exists, mock_remove):
    with patch.object(VintedScraper, '_load_or_fetch_cookies'):
        scraper = VintedScraper({"country": "pt"})

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        scraper.session.get.return_value = mock_response
        mock_exists.return_value = True

        assert scraper._fetch_new_cookies() is True

        scraper.session.cookies.clear.assert_called_once()
        mock_remove.assert_called_once_with(scraper.cookie_file)
