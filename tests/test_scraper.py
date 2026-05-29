import pytest
from unittest.mock import patch, MagicMock
from scraper import VintedScraper

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

@patch("scraper.requests.Session")
def test_scraper_search_pagination(mock_session):
    config = {"country": "pt", "delay_between_requests": 0, "results_per_page": 2}
    
    with patch.object(VintedScraper, '_load_or_fetch_cookies'):
        scraper = VintedScraper(config)
        
        # Mock the session.get response
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = {"items": [{"id": 1}, {"id": 2}]}
        
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {"items": [{"id": 3}]} # Menos que per_page -> deve parar
        
        scraper.session.get.side_effect = [mock_response_1, mock_response_2]
        
        params = {"search_text": "test", "per_page": 2}
        items = scraper.search(params, max_pages=3)
        
        # Devem ter sido retornados 3 itens no total
        assert len(items) == 3
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
        mock_success.json.return_value = {"items": [{"id": 1}]}

        scraper.session.get.side_effect = [mock_rate_limit, mock_success]

        items = scraper.search({"search_text": "test", "per_page": 2}, max_pages=1)

        assert items == [{"id": 1}]
        assert scraper.session.get.call_count == 2
        mock_sleep.assert_called_once_with(3.0)

@patch("scraper.requests.Session")
@patch("scraper.time.sleep")
def test_retry_after_is_capped_by_config(mock_session, mock_sleep):
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
        mock_success.json.return_value = {"items": [{"id": 1}]}

        scraper.session.get.side_effect = [mock_rate_limit, mock_success]

        items = scraper.search({"search_text": "test", "per_page": 2}, max_pages=1)

        assert items == [{"id": 1}]
        assert scraper.session.get.call_count == 2
        mock_sleep.assert_called_once_with(2.0)

@patch("scraper.requests.Session")
def test_get_item_details_enriches_description_and_seller_feedback(mock_session):
    html = (
        '<meta name="description" content="iPhone usado em bom estado"/>'
        '\\"feedback_count\\":4,\\"feedback_reputation\\":0.8'
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
        assert enriched["detail_loaded"] is True
