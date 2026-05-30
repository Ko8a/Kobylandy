"""
Kapster.kz scraper — KZ developer aggregator.

API pattern (from DevTools analysis):
  GET /api/developers?city=astana — developer list
  GET /api/complexes?developer_id={id}&city=astana — complexes by developer
  GET /api/apartments?complex_id={id}&status=available — apartment list

HTML structure:
  /developers/astana — developer directory
  /complex/{slug}/ — complex detail with pricing table
"""

import logging
import re
from .base import BaseScraper, safe_price, safe_float

logger = logging.getLogger(__name__)

SITE_BASE = "https://kapster.kz"
API_BASE = "https://kapster.kz/api"


class KapsterScraper(BaseScraper):
    SOURCE_NAME = "kapster.kz"

    def scrape(self) -> list[dict]:
        apartments = []
        developers = self._get_developers()
        logger.info(f"[kapster] Found {len(developers)} developers")
        for dev in developers:
            self._sleep()
            complexes = self._get_complexes(dev)
            for cx in complexes:
                self._sleep()
                flats = self._get_apartments(cx, dev)
                apartments.extend(flats)
        logger.info(f"[kapster] Total: {len(apartments)}")
        return apartments

    def _get_developers(self) -> list[dict]:
        resp = self.get(f"{API_BASE}/developers?city=astana", headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", data.get("developers", []))
                if items:
                    return [{"id": d.get("id"), "name": d.get("name", d.get("title", "")),
                             "slug": d.get("slug", d.get("id", ""))} for d in items]
            except Exception:
                pass
        soup = self.soup(f"{SITE_BASE}/developers/astana")
        if not soup:
            return []
        devs = []
        for card in soup.select(".developer-card, [class*='developer-item'], [class*='DeveloperCard']"):
            link = card.find("a", href=True)
            name = card.find(["h2", "h3", "h4", ".name", ".title"])
            if not link:
                continue
            href = link["href"]
            slug = href.rstrip("/").split("/")[-1]
            devs.append({"id": slug, "slug": slug, "name": name.get_text(strip=True) if name else slug})
        return devs

    def _get_complexes(self, dev: dict) -> list[dict]:
        resp = self.get(f"{API_BASE}/complexes?developer_id={dev.get('id')}&city=astana",
                        headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", data.get("complexes", []))
                if items:
                    return [{"id": c.get("id"), "slug": c.get("slug", c.get("id", "")),
                             "name": c.get("name", c.get("title", "")),
                             "district": c.get("district", c.get("address", "")),
                             "deadline": c.get("deadline", c.get("completion_date", "")),
                             "class": c.get("class", c.get("housing_class", "")),
                             "mortgage": c.get("mortgage", False),
                             "installment": c.get("installment", False)} for c in items]
            except Exception:
                pass
        return []

    def _get_apartments(self, cx: dict, dev: dict) -> list[dict]:
        cx_id = cx.get("id") or cx.get("slug", "")
        cx_url = f"{SITE_BASE}/complex/{cx.get('slug', cx_id)}/"
        terms = []
        if cx.get("mortgage"):
            terms.append("ипотека")
        if cx.get("installment"):
            terms.append("рассрочка")

        resp = self.get(f"{API_BASE}/apartments?complex_id={cx_id}&status=available&limit=100",
                        headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                flats = data if isinstance(data, list) else data.get("data", data.get("apartments", []))
                apartments = []
                for flat in flats:
                    area = safe_float(flat.get("area") or flat.get("square"))
                    price = safe_price(flat.get("price") or flat.get("total_price"))
                    price_m2 = safe_price(flat.get("price_per_sqm"))
                    if price and area and not price_m2:
                        price_m2 = int(price / area)
                    apartments.append(self.new_apt(
                        застройщик=dev.get("name", ""),
                        название_жк=cx.get("name", ""),
                        район_адрес=cx.get("district", ""),
                        ссылка_жк=cx_url,
                        ссылка_квартира=cx_url + f"?flat={flat.get('id', '')}",
                        комнат=flat.get("rooms") or flat.get("bedrooms"),
                        площадь_м2=area,
                        цена_полная_тг=price,
                        цена_за_м2_тг=price_m2,
                        этаж=flat.get("floor"),
                        дом_блок_секция=flat.get("building") or flat.get("block"),
                        срок_сдачи=cx.get("deadline", ""),
                        статус=flat.get("status", "доступно"),
                        отделка=flat.get("finishing"),
                        класс_жилья=cx.get("class", ""),
                        условия_покупки=", ".join(terms) if terms else "уточнить",
                    ))
                return apartments
            except Exception:
                pass

        # HTML fallback
        soup = self.soup(cx_url)
        if not soup:
            return []
        apartments = []
        for row in soup.select("table tr, [class*='apartment-row'], [class*='flat-item']"):
            cols = row.find_all(["td", "div"])
            texts = [c.get_text(strip=True) for c in cols if c.get_text(strip=True)]
            if len(texts) < 3:
                continue
            area_t = next((t for t in texts if re.match(r"^\d+[.,]?\d*\s*м", t, re.I)), None)
            price_t = next((t for t in texts if re.search(r"[₸тТ]|млн", t, re.I)), None)
            area = safe_float(area_t)
            price = safe_price(price_t)
            rooms_t = next((t for t in texts if re.match(r"^[1-5][-–\s]?к", t, re.I) or t in "12345"), None)
            rooms = safe_float(rooms_t) if rooms_t and len(rooms_t) == 1 else None
            apt = self.new_apt(
                застройщик=dev.get("name", ""),
                название_жк=cx.get("name", ""),
                район_адрес=cx.get("district", ""),
                ссылка_жк=cx_url,
                комнат=rooms,
                площадь_м2=area,
                цена_полная_тг=price,
                цена_за_м2_тг=int(price / area) if price and area else None,
                срок_сдачи=cx.get("deadline", ""),
                класс_жилья=cx.get("class", ""),
                условия_покупки=", ".join(terms) if terms else "уточнить",
            )
            apartments.append(apt)
        return apartments
