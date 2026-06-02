import logging
import time
from html import escape

import requests
from resale import calculate_resale_costs

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, destinations: list, config: dict = None):
        self.token = token
        self.destinations = destinations
        self.config = config or {}
        self.resale_config = self.config.get("resale", {})
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.min_delay_seconds = self.config.get("send_delay_seconds", 1.0)
        self.max_retries = self.config.get("send_max_retries", 3)
        self.retry_backoff_seconds = self.config.get("send_retry_backoff_seconds", 5)
        self.last_send_at = 0.0

    def _truncate(self, text: str, max_length: int) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length - 3].rstrip() + "..."

    def _format_message(self, item: dict, search_name: str) -> str:
        title = item.get("title", "Sem titulo")
        price = item.get("price", "N/A")
        if isinstance(price, dict):
            price_val = price.get("amount", price.get("numeric", "N/A"))
            currency = price.get("currency_code", "EUR")
            price_str = f"{price_val} {currency}"
        else:
            price_str = f"{item.get('price_numeric', price)} {item.get('currency', 'EUR')}"

        condition = item.get("status", "N/A")
        city = item.get("city", "N/A")
        age_days = item.get("age_days")
        age_text = f"{age_days} dias" if age_days is not None else "N/A"

        user = item.get("user", {})
        login = user.get("login", "Desconhecido")
        reviews = user.get("feedback_count")
        reputation = user.get("feedback_reputation")
        stars = round(reputation * 5, 1) if reputation is not None else "N/A"
        reviews_text = reviews if reviews is not None else "N/A"

        description = self._truncate(item.get("description", ""), 500)
        url = item.get("url", "")

        resale = calculate_resale_costs(item, self.config)
        is_high_profit = resale.get("enabled") and resale.get("is_high_profit")

        msg = "🚀 <b>BOM LUCRO DETECTADO</b>\n" if is_high_profit else "🔔 <b>NOVA OPORTUNIDADE</b>\n"
        msg += f"🏷️ <b>{escape(str(search_name))}</b>\n\n"
        msg += f"📱 <b>{escape(str(title))}</b>\n"
        msg += f"💶 <b>Preco:</b> {escape(str(price_str))}\n"
        msg += f"✨ <b>Estado:</b> {escape(str(condition))}\n"
        msg += f"📍 <b>Local:</b> {escape(str(city))}\n"
        msg += f"🕒 <b>Idade:</b> {escape(str(age_text))}\n"
        msg += f"⭐ <b>Vendedor:</b> {escape(str(stars))} estrelas ({escape(str(reviews_text))} avaliacoes)\n"
        msg += f"👤 <b>Utilizador:</b> @{escape(str(login))}\n"
        if description:
            msg += f"\n📝 <b>Descricao</b>\n{escape(description)}\n"
        if resale.get("enabled"):
            heading = "🚀 BOM LUCRO - Revenda" if is_high_profit else "📊 Custo revenda"
            msg += f"\n<b>{heading}</b>\n"
            msg += f"• Item: {resale['item_price_eur']:.2f} EUR\n"
            msg += f"• Taxa Vinted: {resale['vinted_fee_eur']:.2f} EUR\n"
            msg += f"• Frete Vinted: {resale['vinted_shipping_eur']:.2f} EUR\n"
            msg += f"• Envio/importacao: {resale['fixed_shipping_eur']:.2f} EUR\n"
            msg += f"💳 <b>Total:</b> {resale['total_eur']:.2f} EUR\n"
            msg += f"🇦🇴 <b>Total Kz:</b> {resale['total_kz']:,.0f} {escape(str(resale['currency']))}\n"
            if resale["sale_min_kz"] is not None and resale["sale_max_kz"] is not None:
                profit_icon = "🔥" if is_high_profit else "💰"
                msg += f"📈 <b>Venda estimada:</b> {resale['sale_min_kz']:,.0f}-{resale['sale_max_kz']:,.0f} {escape(str(resale['currency']))}\n"
                msg += f"{profit_icon} <b>Lucro estimado:</b> {resale['profit_min_kz']:,.0f}-{resale['profit_max_kz']:,.0f} {escape(str(resale['currency']))}\n"
                msg += f"📌 <b>Margem:</b> {resale['margin_min_percent']:.1f}%-{resale['margin_max_percent']:.1f}%\n"
            msg += f"💱 <b>Cambio:</b> 1 EUR = {resale['eur_to_kz']:,.0f} {escape(str(resale['currency']))}\n"
        msg += f"\n🔗 <a href=\"{escape(str(url))}\">Ver listagem</a>"

        return msg

    def _format_photo_caption(self, item: dict, search_name: str) -> str:
        title = item.get("title", "Sem titulo")
        price = item.get("price", "N/A")
        if isinstance(price, dict):
            price_val = price.get("amount", price.get("numeric", "N/A"))
            currency = price.get("currency_code", "EUR")
            price_str = f"{price_val} {currency}"
        else:
            price_str = f"{item.get('price_numeric', price)} {item.get('currency', 'EUR')}"

        url = item.get("url", "")
        resale = calculate_resale_costs(item, self.config)
        prefix = "🚀 <b>BOM LUCRO</b>\n" if resale.get("enabled") and resale.get("is_high_profit") else "🔔 <b>NOVA OPORTUNIDADE</b>\n"
        return (
            f"{prefix}"
            f"🏷️ <b>{escape(str(search_name))}</b> - {escape(str(price_str))}\n"
            f"📱 {escape(str(title))}\n"
            f"🔗 <a href=\"{escape(str(url))}\">Ver listagem</a>"
        )

    def _wait_for_send_slot(self):
        elapsed = time.time() - self.last_send_at
        if elapsed < self.min_delay_seconds:
            time.sleep(self.min_delay_seconds - elapsed)

    def _post(self, method: str, payload: dict):
        url = f"{self.api_url}/{method}"

        for attempt in range(self.max_retries):
            self._wait_for_send_slot()
            response = requests.post(url, data=payload, timeout=10)
            self.last_send_at = time.time()

            if response.status_code == 429:
                retry_after = self.retry_backoff_seconds
                try:
                    retry_after = response.json().get("parameters", {}).get("retry_after", retry_after)
                except ValueError:
                    pass
                logger.warning(f"Telegram rate limit hit. Retrying after {retry_after}s.")
                time.sleep(float(retry_after))
                continue

            if response.status_code >= 500 and attempt < self.max_retries - 1:
                wait_seconds = self.retry_backoff_seconds * (attempt + 1)
                logger.warning(f"Telegram server error {response.status_code}. Retrying after {wait_seconds}s.")
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            return response

        response.raise_for_status()
        return response

    def send_alert(self, item: dict, search_name: str):
        sent_any = False
        for dest in self.destinations:
            chat_id = dest.get("chat_id")
            if not chat_id:
                continue
            sent_any = self.send_alert_to_chat(item, search_name, chat_id) or sent_any
        return sent_any

    def send_text_to_chat(self, chat_id: str, text: str, parse_mode: str = None):
        try:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            self._post("sendMessage", payload)
            logger.info(f"SENT: Text message sent to {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send telegram text to {chat_id}: {e}")
            return False

    def send_alert_to_chat(self, item: dict, search_name: str, chat_id: str):
        message = self._format_message(item, search_name)
        photo_url = None
        photos = item.get("photos", [])
        if photos:
            photo_url = photos[0].get("url")

        try:
            if photo_url:
                photo_caption = self._format_photo_caption(item, search_name)
                payload = {
                    "chat_id": chat_id,
                    "photo": photo_url,
                    "caption": photo_caption,
                    "parse_mode": "HTML"
                }
                try:
                    self._post("sendPhoto", payload)
                except requests.HTTPError as e:
                    logger.warning(f"Photo send failed for item {item.get('id')}; falling back to text: {e}")
                else:
                    if not self.send_text_to_chat(chat_id, message, parse_mode="HTML"):
                        return False
                    logger.info(f"SENT: Alert sent to {chat_id} for item {item.get('id')}")
                    return True

            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            self._post("sendMessage", payload)
            logger.info(f"SENT: Alert sent to {chat_id} for item {item.get('id')}")
            return True
        except Exception as e:
            logger.error(f"Failed to send telegram alert to {chat_id}: {e}")
            return False
