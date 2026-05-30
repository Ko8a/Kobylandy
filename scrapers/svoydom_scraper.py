"""
Svoy Dom scraper (svoydom.kz) — KZ developer.

URL structure:
  /projects/ — list of residential complexes
  /projects/{slug}/ — complex detail with apartments table
  /projects/{slug}/apartments/ — apartments list page

API pattern (Next.js/Nuxt SSR):
  /api/projects?city=astana
  /api/projects/{id}/apartments?status=available
"""

import logging
import re
from .base import BaseScraper, safe_price, safe_float

logger = logging.getLogger(__name__)

SITE_BASE = "https://svoydom.kz"


class SvoyDomScraper(BaseScraper):
    SOURCE_NAME = "svoydom.kz"

    def scrape(self) -> list[dict]:
        apartments = []
        projects = self._get_projects()
        logger.info(f"[svoydom] Found {len(projects)} projects")
        for proj in projects:
            self._sleep()
            flats = self._get_flats(proj)
            apartments.extend(flats)
        logger.info(f"[svoydom] Total: {len(apartments)}")
        return apartments

    def _get_projects(self) -> list[dict]:
        # Try REST API first
        resp = self.get(f"{SITE_BASE}/api/projects?city=astana", headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", data.get("projects", []))
                if items:
                    return [{"id": p.get("id"), "name": p.get("name", p.get("title", "")),
                             "slug": p.get("slug", p.get("id", "")),
                             "developer": p.get("developer", "Svoy Dom"),
                             "district": p.get("district", p.get("address", "")),
                             "deadline": p.get("deadline", p.get("completion_date", "")),
                             "class": p.get("class", p.get("housing_class", "")),
                             "mortgage": p.get("mortgage", False),
                             "installment": p.get("installment", False)} for p in items]
            except Exception:
                pass
        # HTML fallback
        soup = self.soup(f"{SITE_BASE}/projects/")
        if not soup:
            return []
        projects = []
        for card in soup.select(".project-card, .card, [class*='Project'], article"):
            link = card.find("a", href=True)
            name = card.find(["h2", "h3", "h4"])
            if not link:
                continue
            href = link["href"]
            slug = href.rstrip("/").split("/")[-1]
            projects.append({
                "id": slug,
                "slug": slug,
                "name": name.get_text(strip=True) if name else slug,
                "developer": "Svoy Dom",
                "district": "",
                "deadline": "",
                "class": "",
            })
        return projects

    def _get_flats(self, proj: dict) -> list[dict]:
        slug = proj.get("slug") or proj.get("id", "")
        cx_url = f"{SITE_BASE}/projects/{slug}/"
        terms = []
        if proj.get("mortgage"):
            terms.append("ипотека")
        if proj.get("installment"):
            terms.append("рассрочка")

        # Try API
        resp = self.get(f"{SITE_BASE}/api/projects/{slug}/apartments?status=available&limit=100",
                        headers={"Accept": "application/json"})
        if resp:
            try:
                data = resp.json()
                flats = data if isinstance(data, list) else data.get("data", data.get("apartments", []))
                if flats:
                    return [self._flat_from_api(f, proj, cx_url, terms) for f in flats]
            except Exception:
                pass

        # HTML fallback
        soup = self.soup(f"{SITE_BASE}/projects/{slug}/apartments/") or self.soup(cx_url)
        if not soup:
            return []
        apartments = []
        for row in soup.select("tr, [class*='apartment'], [class*='flat']"):
            cols = row.find_all(["td", "div"])
            texts = [c.get_text(strip=True) for c in cols if c.get_text(strip=True)]
            if len(texts) < 3:
                continue
            area = next((safe_float(t) for t in texts if re.match(r"^\d+[\.,]?\d*\s*м", t, re.I)), None)
            price = next((safe_price(t) for t in texts if re.search(r"[₸тТ]|млн|тенге", t, re.I)), None)
            rooms_m = next((re.search(r"(\d)[-–\s]?к", t, re.I) for t in texts if re.search(r"(\d)[-–\s]?к", t, re.I)), None)
            rooms = int(rooms_m.group(1)) if rooms_m else None
            apt = self.new_apt(
                застройщик=proj.get("developer", "Svoy Dom"),
                название_жк=proj.get("name", ""),
                район_адрес=proj.get("district", ""),
                ссылка_жк=cx_url,
                комнат=rooms,
                площадь_м2=area,
                цена_полная_тг=price,
                цена_за_м2_тг=int(price / area) if price and area else None,
                срок_сдачи=proj.get("deadline", ""),
                класс_жилья=proj.get("class", ""),
                условия_покупки=", ".join(terms) if terms else "уточнить",
            )
            apartments.append(apt)
        return apartments

    def _flat_from_api(self, flat: dict, proj: dict, cx_url: str, terms: list) -> dict:
        area = safe_float(flat.get("area") or flat.get("square") or flat.get("total_area"))
        price = safe_price(flat.get("price") or flat.get("total_price"))
        price_m2 = safe_price(flat.get("price_per_sqm") or flat.get("price_m2"))
        if price and area and not price_m2:
            price_m2 = int(price / area)
        return self.new_apt(
            застройщик=proj.get("developer", "Svoy Dom"),
            название_жк=proj.get("name", ""),
            район_адрес=proj.get("district", ""),
            ссылка_жк=cx_url,
            ссылка_квартира=cx_url + f"apartments/{flat.get('id', '')}",
            комнат=flat.get("rooms") or flat.get("bedrooms"),
            площадь_м2=area,
            цена_полная_тг=price,
            цена_за_м2_тг=price_m2,
            этаж=flat.get("floor"),
            дом_блок_секция=flat.get("building") or flat.get("block"),
            срок_сдачи=proj.get("deadline", ""),
            статус=flat.get("status", "доступно"),
            отделка=flat.get("finishing"),
            класс_жилья=proj.get("class", ""),
            условия_покупки=", ".join(terms) if terms else "уточнить",
        )
