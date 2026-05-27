"""
BI Group scraper (bi.group) — major KZ developer.

Known URL structure:
  /ru/special/kvartiry-v-astane — landing with complex cards
  /ru/complex/{slug}/ — complex detail page
  /ru/complex/{slug}/plans/ — floor plans with prices

API endpoints (from DevTools):
  POST /api/complexes/search?city=astana
  GET  /api/complexes/{id}/flats?status=available
  GET  /api/v1/flats?complex_id={id}&city=astana

JS rendered — uses React. Playwright required for full data.
"""

import logging
import re
from .base import BaseScraper, safe_price, safe_float

logger = logging.getLogger(__name__)

SITE_BASE = "https://bi.group"
API_BASE = "https://bi.group/api"


class BiGroupScraper(BaseScraper):
    SOURCE_NAME = "bi.group"

    def scrape(self) -> list[dict]:
        apartments = []

        # Try JSON API first (discovered via network analysis)
        complexes = self._fetch_complexes_api()
        if complexes:
            logger.info(f"[bi.group] API: found {len(complexes)} complexes")
            for cx in complexes:
                self._sleep()
                flats = self._fetch_flats_api(cx)
                apartments.extend(flats)
        else:
            logger.info("[bi.group] API blocked, trying HTML")
            complexes = self._fetch_complexes_html()
            for cx in complexes:
                self._sleep()
                flats = self._fetch_flats_html(cx)
                apartments.extend(flats)

        logger.info(f"[bi.group] Total: {len(apartments)}")
        return apartments

    def _fetch_complexes_api(self) -> list[dict]:
        # BI Group uses Next.js — the _next/data endpoints expose SSR data
        url = f"{SITE_BASE}/_next/data/build-id/ru/special/kvartiry-v-astane.json"
        resp = self.get(url, headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                props = data.get("pageProps", {})
                return props.get("complexes", props.get("projects", []))
            except Exception:
                pass
        # Fallback: direct REST API
        resp = self.get(f"{API_BASE}/complexes?city=astana&limit=50", headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                return data if isinstance(data, list) else data.get("data", [])
            except Exception:
                pass
        return []

    def _fetch_flats_api(self, cx: dict) -> list[dict]:
        cx_id = cx.get("id") or cx.get("slug", "")
        cx_name = cx.get("name") or cx.get("title", "")
        cx_url = f"{SITE_BASE}/ru/complex/{cx.get('slug', cx_id)}/"
        developer = "BI Group"
        district = cx.get("district") or cx.get("address", "")
        deadline = cx.get("deadline") or cx.get("completion_date", "")
        housing_class = cx.get("class") or cx.get("housing_class", "")
        terms = []
        if cx.get("mortgage"):
            terms.append("ипотека")
        if cx.get("installment"):
            terms.append("рассрочка")
        if cx.get("promo") or cx.get("discount"):
            terms.append("акция")

        apartments = []
        page = 1
        while True:
            url = f"{API_BASE}/complexes/{cx_id}/flats?status=available&page={page}&limit=50"
            resp = self.get(url, headers={"Accept": "application/json"})
            if not resp:
                break
            try:
                data = resp.json()
            except Exception:
                break
            flats = data if isinstance(data, list) else data.get("data", data.get("flats", []))
            if not flats:
                break
            for flat in flats:
                area = safe_float(flat.get("area") or flat.get("total_area") or flat.get("square"))
                price = safe_price(flat.get("price") or flat.get("total_price"))
                price_m2 = safe_price(flat.get("price_per_sqm") or flat.get("price_m2"))
                if price and area and not price_m2:
                    price_m2 = int(price / area)
                apt = self.new_apt(
                    застройщик=developer,
                    название_жк=cx_name,
                    район_адрес=str(district),
                    ссылка_жк=cx_url,
                    ссылка_квартира=cx_url + f"plans/?flat={flat.get('id', '')}",
                    комнат=flat.get("rooms") or flat.get("bedrooms"),
                    площадь_м2=area,
                    цена_полная_тг=price,
                    цена_за_м2_тг=price_m2,
                    этаж=flat.get("floor"),
                    дом_блок_секция=flat.get("building") or flat.get("block"),
                    срок_сдачи=str(deadline),
                    статус=flat.get("status", "доступно"),
                    отделка=flat.get("finishing") or flat.get("decoration"),
                    класс_жилья=str(housing_class),
                    условия_покупки=", ".join(terms) if terms else "уточнить",
                )
                apartments.append(apt)
            total = data.get("total", 0) if isinstance(data, dict) else 0
            if len(apartments) >= total or len(flats) < 50:
                break
            page += 1
            self._sleep()
        return apartments

    def _fetch_complexes_html(self) -> list[dict]:
        soup = self.soup(f"{SITE_BASE}/ru/special/kvartiry-v-astane")
        if not soup:
            return []
        complexes = []
        for card in soup.select("[class*='complex'], [class*='project'], [class*='Complex']"):
            link = card.find("a", href=True)
            name = card.find(["h2", "h3", "h4", "[class*='title']", "[class*='name']"])
            if not link:
                continue
            href = link["href"]
            complexes.append({
                "slug": href.rstrip("/").split("/")[-1],
                "name": name.get_text(strip=True) if name else "",
                "url": SITE_BASE + href if href.startswith("/") else href,
            })
        return complexes

    def _fetch_flats_html(self, cx: dict) -> list[dict]:
        url = cx.get("url", "") + "plans/"
        soup = self.soup(url)
        if not soup:
            return []
        apartments = []
        for row in soup.select("tr, [class*='plan-row'], [class*='flat-row']"):
            cols = row.find_all(["td", "div", "span"])
            if len(cols) < 3:
                continue
            texts = [c.get_text(strip=True) for c in cols]
            rooms_match = re.search(r"(\d)[-–\s]?(?:комн|ком|к\b)", texts[0], re.I) if texts else None
            rooms = int(rooms_match.group(1)) if rooms_match else safe_float(texts[0])
            area = safe_float(texts[1]) if len(texts) > 1 else None
            price = safe_price(texts[2]) if len(texts) > 2 else None
            apt = self.new_apt(
                застройщик="BI Group",
                название_жк=cx.get("name", ""),
                ссылка_жк=cx.get("url", ""),
                комнат=rooms,
                площадь_м2=area,
                цена_полная_тг=price,
                цена_за_м2_тг=int(price / area) if price and area else None,
            )
            apartments.append(apt)
        return apartments
