"""
Krisha.kz scraper — largest KZ real estate portal.

API pattern (found via DevTools > Network):
  GET /a/ajax/zastroyshik/search/?region=2&limit=20&page=1
  GET /zastroyshik/{developer_id}/  — HTML page with projects
  GET /a/ajax/zastroyshik/complex/?developer_id={id}&region=2

HTML fallback:
  /zastroyshik/search/astana/  — developer directory
  /kompleksy/astana/  — complex listings with prices
"""

import logging
import re
from .base import BaseScraper, safe_price, safe_float

logger = logging.getLogger(__name__)

SITE_BASE = "https://krisha.kz"
REGION_ID = 2  # Astana


class KrishaScraper(BaseScraper):
    SOURCE_NAME = "krisha.kz"

    def scrape(self) -> list[dict]:
        apartments = []

        # Strategy 1: get developer list, then complexes, then flats
        developers = self._fetch_developers()
        logger.info(f"[krisha] Found {len(developers)} developers")

        for dev in developers:
            self._sleep()
            complexes = self._fetch_complexes(dev)
            for cx in complexes:
                self._sleep()
                flats = self._fetch_complex_flats(cx, dev)
                apartments.extend(flats)

        # Strategy 2: direct complex listing as fallback
        if not apartments:
            logger.info("[krisha] Falling back to direct complex listing")
            apartments = self._fetch_from_listing()

        logger.info(f"[krisha] Total: {len(apartments)} apartments")
        return apartments

    def _fetch_developers(self) -> list[dict]:
        developers = []
        page = 1
        while True:
            url = f"{SITE_BASE}/zastroyshik/search/astana/?page={page}"
            soup = self.soup(url)
            if not soup:
                break
            cards = soup.select(".developer-item, .zastroyshik-item, [class*='developer']")
            if not cards:
                # Try JSON API
                api_url = f"{SITE_BASE}/a/ajax/zastroyshik/search/?region={REGION_ID}&limit=20&page={page}"
                resp = self.get(api_url, headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
                if resp:
                    try:
                        data = resp.json()
                        items = data.get("items", data.get("developers", []))
                        if not items:
                            break
                        for item in items:
                            developers.append({
                                "id": item.get("id"),
                                "name": item.get("name") or item.get("title", ""),
                                "url": SITE_BASE + f"/zastroyshik/{item.get('id')}/",
                            })
                        page += 1
                        self._sleep()
                        continue
                    except Exception:
                        pass
                break
            for card in cards:
                link = card.find("a", href=True)
                name = card.find(["h2", "h3", ".name", ".title"])
                if link:
                    href = link["href"]
                    developers.append({
                        "id": href.split("/")[-2] if href.endswith("/") else href.split("/")[-1],
                        "name": name.get_text(strip=True) if name else "",
                        "url": SITE_BASE + href if href.startswith("/") else href,
                    })
            next_link = soup.select_one("a[rel='next'], .next-page, [class*='pagination'] a:last-child")
            if not next_link:
                break
            page += 1
            self._sleep()
        return developers

    def _fetch_complexes(self, dev: dict) -> list[dict]:
        complexes = []
        api_url = f"{SITE_BASE}/a/ajax/zastroyshik/complex/?developer_id={dev.get('id', '')}&region={REGION_ID}"
        resp = self.get(api_url, headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
        if resp:
            try:
                data = resp.json()
                items = data.get("items", data.get("complexes", []))
                for item in items:
                    complexes.append({
                        "id": item.get("id"),
                        "name": item.get("name") or item.get("title", ""),
                        "developer": dev.get("name", ""),
                        "url": SITE_BASE + f"/kompleksy/{item.get('slug', item.get('id'))}/",
                        "district": item.get("district") or item.get("address", ""),
                        "deadline": item.get("deadline") or item.get("completion_date", ""),
                        "housing_class": item.get("class", ""),
                        "mortgage": item.get("mortgage", False),
                        "installment": item.get("installment", False),
                    })
                return complexes
            except Exception:
                pass
        # HTML fallback
        soup = self.soup(dev.get("url", ""))
        if not soup:
            return complexes
        for card in soup.select(".complex-item, [class*='complex'], [class*='project']"):
            link = card.find("a", href=True)
            name = card.find(["h2", "h3", "h4"])
            if link:
                complexes.append({
                    "id": "",
                    "name": name.get_text(strip=True) if name else "",
                    "developer": dev.get("name", ""),
                    "url": SITE_BASE + link["href"] if link["href"].startswith("/") else link["href"],
                    "district": "",
                    "deadline": "",
                    "housing_class": "",
                })
        return complexes

    def _fetch_complex_flats(self, cx: dict, dev: dict) -> list[dict]:
        soup = self.soup(cx.get("url", ""))
        if not soup:
            return []
        apartments = []
        rows = soup.select(".flat-row, tr.flat, [class*='apartment-row'], table.price-table tr")
        terms = []
        if cx.get("mortgage"):
            terms.append("ипотека")
        if cx.get("installment"):
            terms.append("рассрочка")
        for row in rows[1:]:
            cols = row.find_all(["td", "div", "span"])
            texts = [c.get_text(strip=True) for c in cols]
            if not texts:
                continue
            area = None
            price = None
            rooms = None
            floor = None
            for text in texts:
                if re.match(r"^\d[\d,.]+ м²?$", text) or re.match(r"^\d+[\.,]\d+$", text):
                    area = safe_float(text)
                elif re.match(r"^[\d\s]+ [тТ₸]", text) or "млн" in text:
                    price = safe_price(text)
                elif re.match(r"^[1-5][-–]ком", text, re.I) or text in ["1", "2", "3", "4", "5"]:
                    rooms = safe_float(text)
                elif re.match(r"^\d+(/\d+)?$", text) and int(text.split("/")[0]) < 50:
                    floor = text
            apt = self.new_apt(
                застройщик=dev.get("name", ""),
                название_жк=cx.get("name", ""),
                район_адрес=cx.get("district", ""),
                ссылка_жк=cx.get("url", ""),
                комнат=rooms,
                площадь_м2=area,
                цена_полная_тг=price,
                цена_за_м2_тг=int(price / area) if price and area else None,
                этаж=floor,
                срок_сдачи=cx.get("deadline", ""),
                класс_жилья=cx.get("housing_class", ""),
                условия_покупки=", ".join(terms) if terms else "уточнить",
            )
            apartments.append(apt)
        return apartments

    def _fetch_from_listing(self) -> list[dict]:
        apartments = []
        page = 1
        while page <= 5:
            url = f"{SITE_BASE}/kompleksy/astana/?page={page}"
            soup = self.soup(url)
            if not soup:
                break
            cards = soup.select(".complex-card, [class*='ComplexCard'], [class*='complex-item']")
            if not cards:
                break
            for card in cards:
                name_el = card.find(["h2", "h3", ".title"])
                price_el = card.find(class_=lambda x: x and "price" in str(x).lower())
                area_el = card.find(class_=lambda x: x and "area" in str(x).lower())
                link_el = card.find("a", href=True)
                developer_el = card.find(class_=lambda x: x and "developer" in str(x).lower())
                price = safe_price(price_el.get_text() if price_el else "")
                area = safe_float(area_el.get_text() if area_el else "")
                apt = self.new_apt(
                    застройщик=developer_el.get_text(strip=True) if developer_el else "",
                    название_жк=name_el.get_text(strip=True) if name_el else "",
                    ссылка_жк=SITE_BASE + link_el["href"] if link_el and link_el["href"].startswith("/") else (link_el["href"] if link_el else ""),
                    цена_полная_тг=price,
                    площадь_м2=area,
                    цена_за_м2_тг=int(price / area) if price and area else None,
                )
                apartments.append(apt)
            page += 1
            self._sleep()
        return apartments
