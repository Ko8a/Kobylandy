"""
Scrapers for: Qazaqstroy, Sensata, Ramsqz, GBG, SAT-NS.

All share similar patterns:
- React/Vue SPA or Next.js SSR
- Internal REST APIs at /api/...
- HTML fallback parsing

Each site gets its own class.
"""

import logging
import re
from .base import BaseScraper, safe_price, safe_float

logger = logging.getLogger(__name__)


class QazaqstroyScraper(BaseScraper):
    """qazaqstroy.kz — developer with multiple complexes in Astana."""

    SOURCE_NAME = "qazaqstroy.kz"
    SITE_BASE = "https://qazaqstroy.kz"

    def scrape(self) -> list[dict]:
        apartments = []
        # Try direct API
        resp = self.get(f"{self.SITE_BASE}/api/apartments?city=astana&language=ru",
                        headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", data.get("items", []))
                for item in items:
                    apartments.append(self._parse_item(item))
                if apartments:
                    logger.info(f"[qazaqstroy] API: {len(apartments)} apartments")
                    return apartments
            except Exception:
                pass
        # Try HTML
        soup = self.soup(f"{self.SITE_BASE}/ru/kvartiry")
        if not soup:
            logger.warning("[qazaqstroy] Could not fetch HTML")
            return []
        for card in soup.select(".apartment-card, .flat-card, [class*='ApartmentCard'], [class*='flat-item']"):
            link = card.find("a", href=True)
            name_el = card.select_one("[class*='name'], [class*='title'], h3, h4")
            price_el = card.select_one("[class*='price']")
            area_el = card.select_one("[class*='area'], [class*='square']")
            rooms_el = card.select_one("[class*='room']")
            cx_el = card.select_one("[class*='complex'], [class*='project']")
            price = safe_price(price_el.get_text() if price_el else "")
            area = safe_float(area_el.get_text() if area_el else "")
            rooms_t = rooms_el.get_text(strip=True) if rooms_el else ""
            rooms_m = re.search(r"(\d)", rooms_t)
            apt = self.new_apt(
                застройщик="Qazaqstroy",
                название_жк=cx_el.get_text(strip=True) if cx_el else (name_el.get_text(strip=True) if name_el else ""),
                ссылка_квартира=self.SITE_BASE + link["href"] if link and link["href"].startswith("/") else (link["href"] if link else ""),
                комнат=int(rooms_m.group(1)) if rooms_m else None,
                площадь_м2=area,
                цена_полная_тг=price,
                цена_за_м2_тг=int(price / area) if price and area else None,
            )
            apartments.append(apt)
        logger.info(f"[qazaqstroy] HTML: {len(apartments)} apartments")
        return apartments

    def _parse_item(self, item: dict) -> dict:
        area = safe_float(item.get("area") or item.get("square"))
        price = safe_price(item.get("price") or item.get("total_price"))
        price_m2 = safe_price(item.get("price_per_sqm"))
        if price and area and not price_m2:
            price_m2 = int(price / area)
        cx = item.get("complex", {}) or {}
        cx_name = cx.get("name", item.get("complex_name", "")) if isinstance(cx, dict) else str(cx)
        return self.new_apt(
            застройщик="Qazaqstroy",
            название_жк=cx_name,
            район_адрес=item.get("district", item.get("address", "")),
            ссылка_квартира=f"{self.SITE_BASE}/ru/kvartiry/{item.get('id', item.get('slug', ''))}",
            комнат=item.get("rooms") or item.get("bedrooms"),
            площадь_м2=area,
            цена_полная_тг=price,
            цена_за_м2_тг=price_m2,
            этаж=item.get("floor"),
            срок_сдачи=item.get("deadline", ""),
            статус=item.get("status", "доступно"),
            отделка=item.get("finishing"),
            класс_жилья=item.get("class", ""),
        )


class SensataScraper(BaseScraper):
    """sensata.kz — boutique developer in Astana."""

    SOURCE_NAME = "sensata.kz"
    SITE_BASE = "https://sensata.kz"

    def scrape(self) -> list[dict]:
        apartments = []
        # API attempts
        for api_path in ["/api/flats", "/api/apartments", "/api/v1/apartments"]:
            resp = self.get(f"{self.SITE_BASE}{api_path}?city=astana",
                            headers={"Accept": "application/json"})
            if resp and resp.status_code == 200:
                try:
                    data = resp.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    if items:
                        for item in items:
                            area = safe_float(item.get("area") or item.get("square"))
                            price = safe_price(item.get("price"))
                            apartments.append(self.new_apt(
                                застройщик="Sensata",
                                название_жк=item.get("complex", item.get("project", "")),
                                район_адрес=item.get("district", item.get("address", "")),
                                комнат=item.get("rooms"),
                                площадь_м2=area,
                                цена_полная_тг=price,
                                цена_за_м2_тг=int(price / area) if price and area else None,
                                этаж=item.get("floor"),
                                срок_сдачи=item.get("deadline", ""),
                                статус=item.get("status", "доступно"),
                                класс_жилья=item.get("class", "бизнес"),
                            ))
                        logger.info(f"[sensata] API {api_path}: {len(apartments)} apartments")
                        return apartments
                except Exception:
                    pass
                self._sleep()
        # HTML
        soup = self.soup(f"{self.SITE_BASE}/")
        if not soup:
            return []
        for card in soup.select(".flat, .apartment, [class*='flat'], [class*='apartment']"):
            price_el = card.select_one("[class*='price']")
            area_el = card.select_one("[class*='area'], [class*='square']")
            price = safe_price(price_el.get_text() if price_el else "")
            area = safe_float(area_el.get_text() if area_el else "")
            apartments.append(self.new_apt(
                застройщик="Sensata",
                цена_полная_тг=price,
                площадь_м2=area,
                цена_за_м2_тг=int(price / area) if price and area else None,
            ))
        logger.info(f"[sensata] HTML: {len(apartments)} apartments")
        return apartments


class RamsqzScraper(BaseScraper):
    """ramsqz.com — developer with projects in Astana."""

    SOURCE_NAME = "ramsqz.com"
    SITE_BASE = "https://ramsqz.com"

    def scrape(self) -> list[dict]:
        apartments = []
        # Try API
        resp = self.get(f"{self.SITE_BASE}/api/apartments?language=ru",
                        headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", data.get("apartments", []))
                for item in items:
                    area = safe_float(item.get("area") or item.get("square"))
                    price = safe_price(item.get("price"))
                    apartments.append(self.new_apt(
                        застройщик="Rams",
                        название_жк=item.get("complex", item.get("project", "")),
                        район_адрес=item.get("district", ""),
                        комнат=item.get("rooms"),
                        площадь_м2=area,
                        цена_полная_тг=price,
                        цена_за_м2_тг=int(price / area) if price and area else None,
                        этаж=item.get("floor"),
                        срок_сдачи=item.get("deadline", ""),
                        статус=item.get("status", "доступно"),
                        отделка=item.get("finishing"),
                        класс_жилья=item.get("class", ""),
                    ))
                if apartments:
                    return apartments
            except Exception:
                pass
        # HTML
        soup = self.soup(f"{self.SITE_BASE}/ru/home")
        if not soup:
            return []
        for card in soup.select("[class*='apartment'], [class*='flat'], [class*='unit']"):
            price_el = card.select_one("[class*='price']")
            area_el = card.select_one("[class*='area']")
            price = safe_price(price_el.get_text() if price_el else "")
            area = safe_float(area_el.get_text() if area_el else "")
            apartments.append(self.new_apt(
                застройщик="Rams",
                цена_полная_тг=price,
                площадь_м2=area,
                цена_за_м2_тг=int(price / area) if price and area else None,
            ))
        return apartments


class GBGScraper(BaseScraper):
    """gbg.kz — Grand Business Group, developer in Astana."""

    SOURCE_NAME = "gbg.kz"
    SITE_BASE = "https://gbg.kz"

    def scrape(self) -> list[dict]:
        apartments = []
        for api_path in ["/api/apartments?city=astana", "/api/flats?city=astana", "/api/v1/flats"]:
            resp = self.get(f"{self.SITE_BASE}{api_path}", headers={"Accept": "application/json"})
            if resp and resp.status_code == 200:
                try:
                    data = resp.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    if items:
                        for item in items:
                            area = safe_float(item.get("area") or item.get("square"))
                            price = safe_price(item.get("price"))
                            cx = item.get("complex", {}) if isinstance(item.get("complex"), dict) else {}
                            apartments.append(self.new_apt(
                                застройщик="GBG",
                                название_жк=cx.get("name", item.get("complex_name", "")),
                                район_адрес=item.get("district", item.get("address", "")),
                                комнат=item.get("rooms"),
                                площадь_м2=area,
                                цена_полная_тг=price,
                                цена_за_м2_тг=int(price / area) if price and area else None,
                                этаж=item.get("floor"),
                                срок_сдачи=item.get("deadline", ""),
                                статус=item.get("status", "доступно"),
                                класс_жилья=item.get("class", ""),
                            ))
                        return apartments
                except Exception:
                    pass
                self._sleep()
        soup = self.soup(f"{self.SITE_BASE}/astana")
        if not soup:
            return []
        for card in soup.select("[class*='flat'], [class*='apartment'], [class*='unit']"):
            price_el = card.select_one("[class*='price']")
            area_el = card.select_one("[class*='area']")
            rooms_el = card.select_one("[class*='room']")
            price = safe_price(price_el.get_text() if price_el else "")
            area = safe_float(area_el.get_text() if area_el else "")
            rooms_t = rooms_el.get_text(strip=True) if rooms_el else ""
            rooms_m = re.search(r"(\d)", rooms_t)
            apartments.append(self.new_apt(
                застройщик="GBG",
                комнат=int(rooms_m.group(1)) if rooms_m else None,
                площадь_м2=area,
                цена_полная_тг=price,
                цена_за_м2_тг=int(price / area) if price and area else None,
            ))
        return apartments


class SatNsScraper(BaseScraper):
    """sat-ns.kz — SAT Development, developer in Astana."""

    SOURCE_NAME = "sat-ns.kz"
    SITE_BASE = "https://sat-ns.kz"

    def scrape(self) -> list[dict]:
        apartments = []
        # Projects page
        resp = self.get(f"{self.SITE_BASE}/api/projects", headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                projects = data if isinstance(data, list) else data.get("data", data.get("projects", []))
                for proj in projects:
                    self._sleep()
                    proj_id = proj.get("id") or proj.get("slug", "")
                    resp_flats = self.get(f"{self.SITE_BASE}/api/projects/{proj_id}/flats",
                                          headers={"Accept": "application/json"})
                    if resp_flats:
                        try:
                            flats_data = resp_flats.json()
                            flats = flats_data if isinstance(flats_data, list) else flats_data.get("data", [])
                            for flat in flats:
                                area = safe_float(flat.get("area") or flat.get("square"))
                                price = safe_price(flat.get("price"))
                                apartments.append(self.new_apt(
                                    застройщик="SAT Development",
                                    название_жк=proj.get("name", ""),
                                    район_адрес=proj.get("district", proj.get("address", "")),
                                    комнат=flat.get("rooms"),
                                    площадь_м2=area,
                                    цена_полная_тг=price,
                                    цена_за_м2_тг=int(price / area) if price and area else None,
                                    этаж=flat.get("floor"),
                                    срок_сдачи=proj.get("deadline", ""),
                                    статус=flat.get("status", "доступно"),
                                    класс_жилья=proj.get("class", ""),
                                ))
                        except Exception:
                            pass
                if apartments:
                    return apartments
            except Exception:
                pass
        # HTML fallback
        soup = self.soup(f"{self.SITE_BASE}/")
        if not soup:
            return []
        for card in soup.select("[class*='flat'], [class*='apartment']"):
            price_el = card.select_one("[class*='price']")
            area_el = card.select_one("[class*='area']")
            price = safe_price(price_el.get_text() if price_el else "")
            area = safe_float(area_el.get_text() if area_el else "")
            apartments.append(self.new_apt(
                застройщик="SAT Development",
                цена_полная_тг=price,
                площадь_м2=area,
                цена_за_м2_тг=int(price / area) if price and area else None,
            ))
        return apartments
