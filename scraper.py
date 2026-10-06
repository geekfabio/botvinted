import requests
import time
import os
import json
import logging
import random
import re
import threading
from html import unescape
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urljoin
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class _CatalogHTMLParser(HTMLParser):
    """Extract listing fields from Vinted's current server-rendered catalog."""

    ITEM_ID_PATTERN = re.compile(r"product-item-id-(\d+)")
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items = []
        self.current = None
        self.depth = 0
        self.text_targets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        test_id = attrs.get("data-testid", "")
        if self.current is None:
            match = self.ITEM_ID_PATTERN.fullmatch(test_id)
            if tag == "div" and match:
                self.current = {"id": match.group(1), "_text": {}}
                self.depth = 1
            return

        if tag not in self.VOID_TAGS:
            self.depth += 1
        if tag == "a" and "--overlay-link" in test_id:
            href = attrs.get("href")
            if href:
                self.current["url"] = urljoin(self.base_url, href)
            self.current["_link_title"] = attrs.get("title", "")
        elif tag == "img" and "--image--img" in test_id:
            image_url = attrs.get("src")
            if image_url:
                self.current["photo_url"] = image_url

        if test_id.endswith("--description-title"):
            field = "title"
        elif test_id.endswith("--description-subtitle"):
            field = "status"
        elif test_id.endswith("--price-text"):
            field = "price_text"
        else:
            field = None
        if field:
            self.current["_text"].setdefault(field, [])
            self.text_targets.append((self.depth, field))

    def handle_endtag(self, tag):
        if self.current is None:
            return
        if self.depth == 1:
            self._finish_item()
            self.current = None
            self.depth = 0
            self.text_targets = []
            return
        self.text_targets = [target for target in self.text_targets if target[0] != self.depth]
        self.depth -= 1

    def handle_data(self, data):
        if self.current is not None:
            for _, field in self.text_targets:
                self.current["_text"][field].append(data)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def _finish_item(self):
        item = self.current
        item_text = item.pop("_text", {})
        title = " ".join(" ".join(item_text.get("title", [])).split())
        link_title = item.pop("_link_title", "")
        if not title:
            title = re.split(
                r",\s*(?:Marca|Brand|Marque|Marke|Merk):",
                link_title,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
        if link_title:
            item["_details_title"] = link_title
        status = " ".join(" ".join(item_text.get("status", [])).split())
        price_text = " ".join(" ".join(item_text.get("price_text", [])).split())
        if title:
            item["title"] = title
        if status:
            item["status"] = status
        if price_text:
            item["_price_text"] = price_text
        self.items.append(item)


class VintedScraper:
    def __init__(self, config: dict):
        self.config = config
        self.timeout_seconds = int(self.config.get("timeout_seconds", 30))
        self.country = config.get("country", "pt").lower()
        self.domain = f"vinted.{self.country}"
        self.base_url = f"https://www.{self.domain}"
        # Vinted's current marketplace serves catalog results as HTML.
        self.catalog_url = f"{self.base_url}/catalog"
        
        self.session = requests.Session()
        self.request_lock = threading.RLock()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        })
        
        self.cookie_file = "data/cookies.json"

        self._load_or_fetch_cookies()


    def _fetch_new_cookies(self):
        """Faz um GET inicial à página da Vinted para obter os cookies de sessão."""
        logger.info(f"Fetching new cookies from {self.base_url}...")
        with self.request_lock:
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
        with self.request_lock:
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
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code in (404, 410):
                logger.warning(f"Item detail unavailable {url}: HTTP {status_code}")
                item["unavailable"] = True
                item["detail_error_status"] = status_code
            else:
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
        item_id = re.escape(str(enriched.get("id", "")))
        if item_id:
            login_match = re.search(
                rf'\\"item_id\\":\\"{item_id}\\",\\"name\\":\\"([^\\"]+)',
                html,
            )
            if login_match:
                user["login"] = login_match.group(1)
        enriched["user"] = user

        created_ts = self._extract_created_timestamp(enriched, html)
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

    def _extract_created_timestamp(self, item: dict, html: str = ""):
        for path in (
            ("created_at_ts",),
            ("created_at_timestamp",),
            ("photo", "high_resolution", "timestamp"),
        ):
            value = item
            for key in path:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(key)
            if isinstance(value, (int, float)):
                timestamp = int(value)
                if 946684800 <= timestamp <= int(time.time()) + (24 * 60 * 60):
                    return timestamp

        upload_date = re.search(
            r'\\"code\\":\\"upload_date\\",\\"data\\":\{\\"title\\":\\"[^\\"]*\\",\\"value\\":\\"([^\\"]+)',
            html,
            re.IGNORECASE,
        )
        if upload_date:
            age_text = unescape(upload_date.group(1)).lower()
            units = {
                "segundo": 1, "second": 1,
                "minuto": 60, "minute": 60,
                "hora": 3600, "hour": 3600,
                "dia": 86400, "día": 86400, "day": 86400,
                "semana": 604800, "week": 604800,
                "mês": 2592000, "mes": 2592000, "month": 2592000,
                "ano": 31536000, "año": 31536000, "year": 31536000,
            }
            relative_age = re.search(
                r"(?:há|hace|il y a)\s*(\d+)\s*([a-záéíóúãõç]+)|"
                r"(\d+)\s*([a-z]+)\s+ago",
                age_text,
            )
            if relative_age:
                amount = int(relative_age.group(1) or relative_age.group(3))
                unit = (relative_age.group(2) or relative_age.group(4)).rstrip("s")
                seconds = next(
                    (value for name, value in units.items() if unit.startswith(name)),
                    None,
                )
                if seconds is not None:
                    return max(0, int(time.time()) - amount * seconds)
            if any(text in age_text for text in ("agora", "just now", "maintenant")):
                return int(time.time())
        return None

    def search(self, params: dict, max_pages: int = 1) -> list:
        """
        Executa a pesquisa e lida com a paginação.
        Retorna uma lista de items.
        """
        all_items = []
        delay = self.config.get("delay_between_requests", 2)
        per_page = max(1, int(params.get("per_page", 96)))
        currency = params.get("currency", self.config.get("currency", "EUR"))
        
        for page in range(1, max_pages + 1):
            page_params = dict(params)
            page_params["page"] = page
            full_url = f"{self.catalog_url}?{urlencode(page_params, doseq=True)}"
            
            logger.debug(f"Scraping page {page}: {full_url}")
            
            try:
                response = self._request_with_retry(full_url)
                response.raise_for_status()
                parser = _CatalogHTMLParser(self.base_url)
                parser.feed(response.text)
                items = []
                seen_ids = set()
                for parsed_item in parser.items:
                    item_id = parsed_item.get("id")
                    if not item_id or item_id in seen_ids or not parsed_item.get("url"):
                        continue
                    seen_ids.add(item_id)
                    price_text = parsed_item.pop("_price_text", "")
                    details_title = parsed_item.pop("_details_title", "")
                    if not parsed_item.get("status"):
                        status_match = re.search(
                            r"(?:Estado|Condition|État|Zustand|Condición|Condizione):\s*([^,]+)",
                            details_title,
                            re.IGNORECASE,
                        )
                        if status_match:
                            parsed_item["status"] = status_match.group(1).strip()
                    if not price_text:
                        price_match = re.search(
                            r"(?:Estado|Condition|État|Zustand|Condición|Condizione):\s*[^,]+,\s*([\d.,]+)\s*(?:€|EUR|£|\$|zł|Kč|Ft|CHF)",
                            details_title,
                            re.IGNORECASE,
                        )
                        if price_match:
                            price_text = price_match.group(1)
                    amount_match = re.search(r"\d[\d\s.,]*", price_text)
                    if amount_match:
                        amount = amount_match.group(0).replace(" ", "").replace("\xa0", "")
                        if "," in amount and "." in amount:
                            decimal_separator = "," if amount.rfind(",") > amount.rfind(".") else "."
                            thousands_separator = "." if decimal_separator == "," else ","
                            amount = amount.replace(thousands_separator, "").replace(decimal_separator, ".")
                        elif "," in amount:
                            amount = amount.replace(".", "").replace(",", ".")
                        try:
                            parsed_item["price"] = {
                                "amount": f"{float(amount):.2f}",
                                "currency_code": currency,
                            }
                        except ValueError:
                            pass
                    photo_url = parsed_item.pop("photo_url", None)
                    parsed_item["photos"] = [{"url": photo_url}] if photo_url else []
                    parsed_item["user"] = {}
                    items.append(parsed_item)
                    if len(items) >= per_page:
                        break

                all_items.extend(items)
                
                # Se não houver mais items, ou se vieram menos items do que o pedido, parar a paginação
                if not items or len(items) < per_page:
                    break
                    
                if page < max_pages:
                    time.sleep(delay)
                    
            except Exception as e:
                logger.error(f"Error scraping {full_url}: {e}")
                break
                
        return all_items
