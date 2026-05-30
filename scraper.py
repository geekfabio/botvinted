import requests
import time
import os
import json
import logging
import random
import re
from html import unescape
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

class VintedScraper:
    def __init__(self, config: dict):
        self.config = config
        self.timeout_seconds = int(self.config.get("timeout_seconds", 30))
        self.country = config.get("country", "pt").lower()
        self.domain = f"vinted.{self.country}"
        self.base_url = f"https://www.{self.domain}"
        self.api_url = f"{self.base_url}/api/v2/catalog/items"
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
        })
        
        self.cookie_file = "data/cookies.json"
        self._load_or_fetch_cookies()

    def _fetch_new_cookies(self):
        """Faz um GET inicial à página da Vinted para obter os cookies de sessão."""
        logger.info(f"Fetching new cookies from {self.base_url}...")
        try:
            self.session.cookies.clear()
            if os.path.exists(self.cookie_file):
                os.remove(self.cookie_file)

            # Precisamos apenas bater na homepage para a Vinted atribuir os cookies
            response = self.session.get(self.base_url, timeout=15)
            response.raise_for_status()
            
            # Guardar os cookies num ficheiro
            cookies_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
            
            os.makedirs(os.path.dirname(self.cookie_file), exist_ok=True)
            with open(self.cookie_file, "w") as f:
                json.dump(cookies_dict, f)
                
            logger.info("Successfully fetched and saved new cookies.")
            return True
        except Exception as e:
            logger.error(f"Failed to fetch initial cookies: {e}")
            return False

    def _load_or_fetch_cookies(self):
        """Tenta carregar os cookies de ficheiro. Se não existirem, procura novos."""
        if not self.config.get("reuse_saved_cookies", False):
            self._fetch_new_cookies()
            return

        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, "r") as f:
                    cookies_dict = json.load(f)
                self.session.cookies.update(cookies_dict)
                logger.info("Loaded cookies from file.")
            except Exception as e:
                logger.error(f"Error loading cookies from file: {e}")
                self._fetch_new_cookies()
        else:
            self._fetch_new_cookies()

    def _get_retry_after_seconds(self, response) -> float:
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if not retry_after:
            return None

        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                return max(0.0, retry_at.timestamp() - time.time())
            except Exception:
                return None

    def _sleep_before_retry(self, attempt: int, response=None, error=None):
        base_delay = self.config.get("retry_backoff_seconds", 60)
        multiplier = self.config.get("retry_backoff_multiplier", 2)
        max_delay = self.config.get("retry_max_backoff_seconds", 900)
        jitter = self.config.get("retry_jitter_seconds", 5)

        retry_after = self._get_retry_after_seconds(response)
        retry_after_max = self.config.get("retry_after_max_seconds", 300)
        if retry_after is not None:
            if isinstance(retry_after_max, (int, float)) and retry_after_max > 0:
                capped_retry_after = min(retry_after, retry_after_max)
                if capped_retry_after != retry_after:
                    logger.warning(
                        f"Retry-After header requested {retry_after:.1f}s, capped to {capped_retry_after:.1f}s by retry_after_max_seconds"
                    )
                wait_seconds = capped_retry_after
            else:
                wait_seconds = retry_after
        else:
            wait_seconds = min(base_delay * (multiplier ** attempt), max_delay)
            if jitter:
                wait_seconds += random.uniform(0, jitter)

        status = response.status_code if response is not None else "network_error"
        reason = error or f"HTTP {status}"
        logger.warning(f"Retrying after {wait_seconds:.1f}s due to {reason}")
        time.sleep(wait_seconds)

    def _request_with_retry(self, url: str):
        max_attempts = max(1, int(self.config.get("retry_max_attempts", 3)))
        retry_status_codes = set(self.config.get("retry_status_codes", [403, 429, 500, 502, 503, 504]))
        cookie_refresh_status_codes = set(self.config.get("cookie_refresh_status_codes", [401]))
        retry_status_codes.update(cookie_refresh_status_codes)

        last_error = None

        for attempt in range(max_attempts):
            try:
                response = self.session.get(url, timeout=self.timeout_seconds)

                if response.status_code in cookie_refresh_status_codes:
                    logger.warning(
                        f"Received {response.status_code}. Cookies might be expired or blocked. Fetching new cookies..."
                    )
                    if self._fetch_new_cookies():
                        response = self.session.get(url, timeout=self.timeout_seconds)

                if response.status_code not in retry_status_codes:
                    return response

                if attempt == max_attempts - 1:
                    return response

                self._sleep_before_retry(attempt, response=response)
            except requests.RequestException as e:
                last_error = e
                if attempt == max_attempts - 1:
                    raise
                if isinstance(e, requests.Timeout):
                    logger.warning("Timeout detected. Refreshing cookies and retrying...")
                    self._fetch_new_cookies()
                elif isinstance(e, requests.TooManyRedirects):
                    logger.warning("Redirect loop detected. Clearing cookies and retrying with a fresh session...")
                    self._fetch_new_cookies()
                self._sleep_before_retry(attempt, error=e)

        if last_error:
            raise last_error
        return response

    def get_item_details(self, item: dict) -> dict:
        """Carrega a pagina do item e junta descricao/rating do vendedor."""
        url = item.get("url")
        if not url:
            item["detail_loaded"] = False
            return item

        try:
            response = self._request_with_retry(url)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Error loading item detail {url}: {e}")
            item["detail_loaded"] = False
            return item

        html = response.text
        enriched = dict(item)
        enriched["detail_loaded"] = True

        description = self._extract_meta_description(html)
        if description:
            enriched["description"] = description

        user = dict(enriched.get("user", {}))
        feedback_count = self._extract_number(html, r'\\"feedback_count\\":(\d+)')
        feedback_reputation = self._extract_number(html, r'\\"feedback_reputation\\":([0-9.]+)', as_float=True)
        if feedback_count is not None:
            user["feedback_count"] = feedback_count
        if feedback_reputation is not None:
            user["feedback_reputation"] = feedback_reputation
        enriched["user"] = user

        created_ts = self._extract_created_timestamp(enriched)
        if created_ts is not None:
            enriched["created_at_ts"] = created_ts
            enriched["age_days"] = max(0, int((time.time() - created_ts) // 86400))

        return enriched

    def _extract_meta_description(self, html: str) -> str:
        match = re.search(r'<meta name="description" content="([^"]*)"', html)
        if not match:
            return ""
        return unescape(match.group(1)).strip()

    def _extract_number(self, text: str, pattern: str, as_float: bool = False):
        match = re.search(pattern, text)
        if not match:
            return None
        value = match.group(1)
        return float(value) if as_float else int(value)

    def _extract_created_timestamp(self, item: dict):
        for path in (
            ("created_at_ts",),
            ("created_at_timestamp",),
            ("search_tracking_params", "score"),
            ("photo", "high_resolution", "timestamp"),
        ):
            value = item
            for key in path:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
        return None

    def search(self, params: dict, max_pages: int = 1) -> list:
        """
        Executa a pesquisa e lida com a paginação.
        Retorna uma lista de items.
        """
        all_items = []
        delay = self.config.get("delay_between_requests", 2)
        
        for page in range(1, max_pages + 1):
            params["page"] = page
            
            # A API da Vinted usa o formato param[]=1&param[]=2 para arrays (status_ids)
            # O requests.get faz urlencode, mas para listas precisamos garantir o formato correcto
            # Para simplificar, construímos a query string manualmente para listas se necessário
            
            query_string = []
            for k, v in params.items():
                if isinstance(v, list):
                    for item in v:
                        query_string.append(f"{k}={item}")
                else:
                    query_string.append(f"{k}={v}")
            
            full_url = f"{self.api_url}?{'&'.join(query_string)}"
            
            logger.debug(f"Scraping page {page}: {full_url}")
            
            try:
                response = self._request_with_retry(full_url)
                response.raise_for_status()
                data = response.json()
                
                items = data.get("items", [])
                all_items.extend(items)
                
                # Se não houver mais items, ou se vieram menos items do que o pedido, parar a paginação
                if not items or len(items) < params.get("per_page", 96):
                    break
                    
                if page < max_pages:
                    time.sleep(delay)
                    
            except Exception as e:
                logger.error(f"Error scraping {full_url}: {e}")
                break
                
        return all_items
