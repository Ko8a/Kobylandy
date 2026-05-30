"""
Homsters.kz scraper — real estate aggregator.

API pattern (REST + GraphQL found via DevTools):
  GET /api/v1/listings?city=astana&type=new_building&page=1&limit=20
  GET /api/v1/complexes?city=astana&page=1
  GET /api/v2/search?location=astana&property_type=apartment&market=primary

HTML structure:
  /estate/search/astana-and-primary — search results
  Each listing card has: .listing-card or .property-card
"""

import logging
import re
from .base import BaseScraper, safe_price, safe_float

logger = logging.getLogger(__name__)

SITE_BASE = "https://homsters.kz"
API_BASE = "https://homsters.kz/api"


class HomstersScraper(BaseScraper):
    SOURCE_NAME = "homsters.kz"

    def scrape(self) -> list[dict]:
        apartments = []

        # Strategy 1: REST API
        api_data = self._fetch_api()
        if api_data:
            apartments.extend(api_data)
        else:
            # Strategy 2: HTML scraping
            apartments.extend(self._fetch_html())

        logger.info(f"[homsters] Total: {len(apartments)}")
        return apartments

    def _fetch_api(self) -> list[dict]:
        apartments = []
        page = 1
        while page <= 10:
            url = f"{API_BASE}/v1/listings?city=astana&type=new_building&page={page}&limit=20"
            resp = self.get(url, headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            })
            if not resp:
                break
            try:
                data = resp.json()
            except Exception:
                break
            items = data.get("listings", data.get("data", data.get("results", [])))
            if not items:
                break
            for item in items:
                apt = self._parse_listing(item)
                apartments.append(apt)
            total_pages = data.get("pages", data.get("total_pages", 1))
            if page >= total_pages:
                break
            page += 1
            self._sleep()
        return apartments

    def _parse_listing(self, item: dict) -> dict:
        area = safe_float(item.get("area") or item.get("total_area") or item.get("square"))
        price = safe_price(item.get("price") or item.get("total_price"))
        price_m2 = safe_price(item.get("price_per_sqm") or item.get("price_m2"))
        if price and area and not price_m2:
            price_m2 = int(price / area)
        cx = item.get("complex", {}) or {}
        dev = item.get("developer", {}) or {}
        terms = []
        if item.get("mortgage") or cx.get("mortgage"):
            terms.append("ипотека")
        if item.get("installment") or cx.get("installment"):
            terms.append("рассрочка")
        return self.new_apt(
            застройщик=dev.get("name", "") if isinstance(dev, dict) else str(dev),
            название_жк=cx.get("name", item.get("complex_name", "")) if isinstance(cx, dict) else item.get("complex_name", ""),
            район_адрес=item.get("district") or item.get("address") or item.get("location", ""),
            ссылка_жк=SITE_BASE + f"/estate/{cx.get('slug', '')}/" if isinstance(cx, dict) and cx.get("slug") else "",
            ссылка_квартира=SITE_BASE + f"/estate/{item.get('slug', item.get('id', ''))}/",
            комнат=item.get("rooms") or item.get("bedrooms"),
            площадь_м2=area,
            цена_полная_тг=price,
            цена_за_м2_тг=price_m2,
            этаж=item.get("floor"),
            дом_блок_секция=item.get("building") or item.get("block"),
            срок_сдачи=item.get("deadline") or item.get("completion_date", ""),
            статус=item.get("status", "доступно"),
            отделка=item.get("finishing") or item.get("decoration"),
            класс_жилья=item.get("class") or (cx.get("class", "") if isinstance(cx, dict) else ""),
            условия_покупки=", ".join(terms) if terms else "уточнить",
        )

    def _fetch_html(self) -> list[dict]:
        apartments = []
        page = 1
        while page <= 5:
            url = f"{SITE_BASE}/estate/search/astana-and-primary?page={page}"
            soup = self.soup(url)
            if not soup:
                break
            cards = soup.select(".listing-card, .property-card, [class*='ListingCard'], [data-listing]")
            if not cards:
                break
            for card in cards:
                price_el = card.select_one("[class*='price'], .price")
                area_el = card.select_one("[class*='area'], .area, [class*='square']")
                rooms_el = card.select_one("[class*='room'], .rooms")
                name_el = card.select_one("[class*='complex'], [class*='title'], h2, h3")
                dev_el = card.select_one("[class*='developer'], .developer")
                link_el = card.find("a", href=True)
                floor_el = card.select_one("[class*='floor']")
                price = safe_price(price_el.get_text() if price_el else "")
                area = safe_float(area_el.get_text() if area_el else "")
                rooms_text = rooms_el.get_text(strip=True) if rooms_el else ""
                rooms_m = re.search(r"(\d)", rooms_text)
                rooms = int(rooms_m.group(1)) if rooms_m else None
                apt = self.new_apt(
                    застройщик=dev_el.get_text(strip=True) if dev_el else "",
                    название_жк=name_el.get_text(strip=True) if name_el else "",
                    ссылка_квартира=SITE_BASE + link_el["href"] if link_el and link_el["href"].startswith("/") else (link_el["href"] if link_el else ""),
                    комнат=rooms,
                    площадь_м2=area,
                    цена_полная_тг=price,
                    цена_за_м2_тг=int(price / area) if price and area else None,
                    этаж=floor_el.get_text(strip=True) if floor_el else None,
                )
                apartments.append(apt)
            next_btn = soup.select_one("a[rel='next'], .pagination-next")
            if not next_btn:
                break
            page += 1
            self._sleep()
        return apartments
