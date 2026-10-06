import pytest
import time
from filters import (
    map_condition,
    item_passes_global_filters,
    item_within_price_range,
    build_search_url_params,
)

def test_map_condition():
    assert map_condition("new") == 1
    assert map_condition("new_without_tags") == 1
    assert map_condition("new_with_tags") == 6
    assert map_condition("like_new") == 2
    assert map_condition("good") == 3
    assert map_condition("satisfactory") == 4
    assert map_condition("nonexistent") is None

def test_item_passes_global_filters_empty_filters():
    item = {"title": "iPhone", "user": {"feedback_reputation": 1.0}}
    assert item_passes_global_filters(item, {}) is True


def test_item_passes_global_filters_rejects_unavailable_item():
    item = {"title": "iPhone", "unavailable": True}
    assert item_passes_global_filters(item, {}) is False
    assert item_passes_global_filters(item, {"seller_min_reviews": 1}) is False

def test_item_passes_global_filters_reputation():
    global_filters = {"seller_min_stars": 4} # Requires 4/5 = 0.8 reputation
    
    # 0.9 > 0.8 -> Pass
    item_pass = {"user": {"feedback_reputation": 0.9}}
    assert item_passes_global_filters(item_pass, global_filters) is True
    
    # 0.7 < 0.8 -> Fail
    item_fail = {"user": {"feedback_reputation": 0.7}}
    assert item_passes_global_filters(item_fail, global_filters) is False

def test_item_passes_global_filters_reviews():
    global_filters = {"seller_min_reviews": 5}
    
    item_pass = {"user": {"feedback_count": 6}}
    assert item_passes_global_filters(item_pass, global_filters) is True
    
    item_fail = {"user": {"feedback_count": 4}}
    assert item_passes_global_filters(item_fail, global_filters) is False

def test_item_passes_global_filters_ignores_missing_seller_feedback():
    global_filters = {"seller_min_stars": 4, "seller_min_reviews": 5}

    item = {"title": "iPhone", "user": {}}
    assert item_passes_global_filters(item, global_filters) is True

def test_item_passes_global_filters_requires_seller_feedback_when_configured():
    global_filters = {
        "seller_min_stars": 3,
        "seller_min_reviews": 1,
        "require_seller_feedback": True,
    }

    item = {"title": "iPhone", "user": {}}
    assert item_passes_global_filters(item, global_filters) is False

def test_item_passes_global_filters_rejects_old_items():
    global_filters = {"max_item_age_days": 14}
    old_ts = int(time.time()) - (15 * 24 * 60 * 60)
    fresh_ts = int(time.time()) - (2 * 24 * 60 * 60)

    assert item_passes_global_filters({"created_at_ts": old_ts}, global_filters) is False
    assert item_passes_global_filters({"created_at_ts": fresh_ts}, global_filters) is True


def test_item_age_uses_photo_timestamp_and_never_ranking_score():
    global_filters = {"max_item_age_days": 14, "require_item_age": True}
    fresh_ts = int(time.time()) - 60
    item = {
        "search_tracking_params": {"score": 1.0038462},
        "photo": {"high_resolution": {"timestamp": fresh_ts}},
    }

    assert item_passes_global_filters(item, global_filters) is True
    assert item_passes_global_filters(
        {"search_tracking_params": {"score": 1.0038462}},
        global_filters,
    ) is False


def test_pre_detail_filter_can_skip_seller_checks():
    global_filters = {
        "require_seller_feedback": True,
        "seller_min_stars": 3,
        "seller_min_reviews": 1,
    }

    assert item_passes_global_filters({"user": {}}, global_filters) is False
    assert item_passes_global_filters(
        {"user": {}}, global_filters, check_seller=False
    ) is True


def test_pre_detail_filter_defers_required_item_age_until_details_are_loaded():
    global_filters = {"max_item_age_days": 14, "require_item_age": True}

    assert item_passes_global_filters(
        {"title": "iPhone", "user": {}},
        global_filters,
        check_seller=False,
        check_item_age=False,
    ) is True
    assert item_passes_global_filters(
        {"title": "iPhone", "user": {}}, global_filters
    ) is False


@pytest.mark.parametrize(
    ("item", "search", "expected"),
    [
        ({"price": {"amount": "50.00"}}, {"price_min": 50, "price_max": 240}, True),
        ({"price": {"amount": "240.00"}}, {"price_min": 50, "price_max": 240}, True),
        ({"price": {"amount": "49.99"}}, {"price_min": 50, "price_max": 240}, False),
        ({"price": {"amount": "240.01"}}, {"price_min": 50, "price_max": 240}, False),
        ({"price_numeric": 125}, {"price_min": 75, "price_max": 125}, True),
        ({"title": "missing price"}, {"price_min": 1}, False),
    ],
)
def test_item_within_configured_price_range(item, search, expected):
    assert item_within_price_range(item, search) is expected

def test_item_passes_global_filters_keywords():
    global_filters = {"exclude_keywords": ["avariado", "partido"]}
    
    item_pass = {"title": "iPhone 13 novo", "description": "Lindo"}
    assert item_passes_global_filters(item_pass, global_filters) is True
    
    item_fail = {"title": "iPhone 13 partido no ecrã", "description": "Funciona"}
    assert item_passes_global_filters(item_fail, global_filters) is False
    
    item_fail2 = {"title": "iPhone", "description": "Está avariado"}
    assert item_passes_global_filters(item_fail2, global_filters) is False

def test_build_search_url_params():
    search_config = {
        "query": "iphone 12",
        "price_min": 100,
        "price_max": 200,
        "condition": ["new", "like_new"]
    }
    scraping_config = {
        "currency": "EUR",
        "results_per_page": 50
    }
    
    params = build_search_url_params(search_config, scraping_config)
    
    assert params["search_text"] == "iphone 12"
    assert params["price_from"] == 100
    assert params["price_to"] == 200
    assert params["currency"] == "EUR"
    assert params["order"] == "newest_first"
    assert params["per_page"] == 50
    assert params["status_ids[]"] == [1, 2]
