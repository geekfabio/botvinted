import time


MIN_REASONABLE_TIMESTAMP = 946684800  # 2000-01-01 UTC


def get_item_created_timestamp(item: dict):
    """Return a real item timestamp, never Vinted's ranking score."""
    candidates = (
        item.get("created_at_ts"),
        item.get("created_at_timestamp"),
        item.get("photo", {}).get("high_resolution", {}).get("timestamp"),
    )
    max_reasonable_timestamp = int(time.time()) + (24 * 60 * 60)
    for value in candidates:
        if isinstance(value, (int, float)):
            timestamp = int(value)
            if MIN_REASONABLE_TIMESTAMP <= timestamp <= max_reasonable_timestamp:
                return timestamp
    return None


def map_condition(condition_str: str) -> int:
    """
    Mapeia uma string de condição para o ID numérico da Vinted.
    Valores aproximados:
    IDs confirmados no catálogo atual da Vinted:
    1 - Novo sem etiquetas (new_without_tags / new)
    2 - Muito bom estado (like_new)
    3 - Bom estado (good)
    4 - Satisfatório (satisfactory)
    6 - Novo com etiquetas (new_with_tags)
    """
    mapping = {
        "new_with_tags": 6,
        "new": 1,
        "new_without_tags": 1,
        "like_new": 2,
        "good": 3,
        "satisfactory": 4
    }
    return mapping.get(condition_str.lower())

def item_passes_global_filters(
    item: dict,
    global_filters: dict,
    check_seller: bool = True,
    check_item_age: bool = True,
) -> bool:
    """
    Verifica se a listagem passa os filtros globais definidos no config.yaml.
    """
    if not global_filters:
        return not item.get("unavailable", False)

    if item.get("unavailable"):
        return False
        
    user = item.get("user", {})
    require_seller_feedback = global_filters.get("require_seller_feedback", False)
    require_item_age = global_filters.get("require_item_age", False)
    
    # 1. Filtro de Estrelas do Vendedor
    # Na Vinted, `feedback_reputation` varia de 0.0 a 1.0
    min_stars = global_filters.get("seller_min_stars")
    if check_seller and min_stars is not None:
        reputation = user.get("feedback_reputation")
        if reputation is None:
            reputation = user.get("feedback_reputation_percent")
            if reputation is not None:
                reputation = reputation / 100.0
        if require_seller_feedback and reputation is None:
            return False
        # Converter estrelas (0-5) para percentagem (0.0 - 1.0)
        min_rep_required = min_stars / 5.0
        if reputation is not None and reputation < min_rep_required:
            return False
            
    # 2. Filtro de Avaliações (Reviews) do Vendedor
    min_reviews = global_filters.get("seller_min_reviews")
    if check_seller and min_reviews is not None:
        reviews_count = user.get("feedback_count")
        if require_seller_feedback and reviews_count is None:
            return False
        if reviews_count is not None and reviews_count < min_reviews:
            return False

    max_item_age_days = global_filters.get("max_item_age_days")
    if check_item_age and max_item_age_days is not None:
        created_ts = get_item_created_timestamp(item)
        if require_item_age and created_ts is None:
            return False
        if created_ts is not None:
            age_seconds = time.time() - int(created_ts)
            if age_seconds > int(max_item_age_days) * 24 * 60 * 60:
                return False
            
    # 3. Exclude Keywords
    exclude_keywords = global_filters.get("exclude_keywords", [])
    title = item.get("title", "").lower()
    description = item.get("description", "").lower()
    
    for kw in exclude_keywords:
        kw = kw.lower()
        if kw in title or kw in description:
            return False
            
    return True


def item_within_price_range(item: dict, search_config: dict) -> bool:
    """Enforce configured price bounds locally, even if Vinted ignores query filters."""
    price = item.get("price")
    if isinstance(price, dict):
        price = price.get("amount", price.get("numeric"))
    if price is None:
        price = item.get("price_numeric")

    try:
        amount = float(str(price).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return False

    price_min = search_config.get("price_min")
    price_max = search_config.get("price_max")
    if price_min is not None and amount < float(price_min):
        return False
    if price_max is not None and amount > float(price_max):
        return False
    return True

def build_search_url_params(search_config: dict, scraping_config: dict) -> dict:
    """
    Constrói os parâmetros para enviar à API da Vinted baseando-se no config.
    """
    params = {
        "search_text": search_config.get("query", ""),
        "currency": scraping_config.get("currency", "EUR"),
        "order": "newest_first", # Importante para alertas
        "per_page": scraping_config.get("results_per_page", 96),
    }
    
    # Preço
    if search_config.get("price_min") is not None:
        params["price_from"] = search_config.get("price_min")
        
    if search_config.get("price_max") is not None:
        params["price_to"] = search_config.get("price_max")
        
    # Condição
    conditions = search_config.get("condition", [])
    if conditions:
        status_ids = []
        for cond in conditions:
            mapped = map_condition(cond)
            if mapped:
                status_ids.append(mapped)
        if status_ids:
            # A API da Vinted aceita listas no formato `status_ids[]`
            params["status_ids[]"] = status_ids
            
    return params
