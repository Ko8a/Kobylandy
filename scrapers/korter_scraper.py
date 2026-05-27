"""
Korter.kz scraper — aggregator with projects and flats.

API pattern (found via DevTools > Network):
  GET /api/v2/projects?city=astana&limit=20&offset=0
  GET /api/v2/projects/{id}/flats?limit=50&offset=0
  GET /api/v2/flats?project_id={id}&rooms=1,2,3&min_area=30

HTML fallback:
  /новостройки-астаны — list of projects (server-side rendered cards)
  /жк/{slug} — individual project page with flat table
"""

import json
import logging
import time
from .base import BaseScraper, safe_price, safe_float

logger = logging.getLogger(__name__)

API_BASE = "https://korter.kz/api/v2"
SITE_BASE = "https://korter.kz"


class KorterScraper(BaseScraper):
    SOURCE_NAME = "korter.kz"

    def scrape(self) -> list[dict]:
        apartments = []

        # Step 1: try JSON API
        projects = self._fetch_projects_api()

        if projects:
            logger.info(f"[korter] API: found {len(projects)} projects")
            for proj in projects:
                self._sleep()
                flats = self._fetch_flats_api(proj)
                apartments.extend(flats)
        else:
            # Step 2: fallback to HTML scraping
            logger.info("[korter] API unavailable, switching to HTML fallback")
            projects_html = self._fetch_projects_html()
            for proj in projects_html:
                self._sleep()
                flats = self._fetch_project_html(proj)
                apartments.extend(flats)

        logger.info(f"[korter] Total collected: {len(apartments)} apartments")
        return apartments

    # ---------- API methods ----------

    def _fetch_projects_api(self) -> list[dict]:
        projects = []
        offset = 0
        limit = 20
        while True:
            url = f"{API_BASE}/projects?city=astana&limit={limit}&offset={offset}"
            resp = self.get(url, headers={"Accept": "application/json"})
            if not resp:
                break
            try:
                data = resp.json()
            except Exception:
                break
            items = data if isinstance(data, list) else data.get("data", data.get("projects", []))
            if not items:
                break
            projects.extend(items)
            if len(items) < limit:
                break
            offset += limit
            self._sleep()
        return projects

    def _fetch_flats_api(self, proj: dict) -> list[dict]:
        proj_id = proj.get("id") or proj.get("slug", "")
        proj_name = proj.get("name") or proj.get("title", "")
        developer = proj.get("developer", {})
        dev_name = developer.get("name", "") if isinstance(developer, dict) else str(developer)
        proj_url = f"{SITE_BASE}/жк/{proj.get('slug', proj_id)}"
        district = proj.get("district") or proj.get("location", {}).get("district", "") if isinstance(proj.get("location"), dict) else proj.get("location", "")
        housing_class = proj.get("housing_class") or proj.get("class", "")
        deadline = proj.get("deadline") or proj.get("completion_date", "")

        apartments = []
        offset = 0
        limit = 50
        while True:
            url = f"{API_BASE}/projects/{proj_id}/flats?limit={limit}&offset={offset}"
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
                area = safe_float(flat.get("area") or flat.get("total_area"))
                price = safe_price(flat.get("price") or flat.get("total_price"))
                price_per_m2 = safe_price(flat.get("price_per_sqm") or flat.get("price_per_m2"))
                if price and area and not price_per_m2:
                    price_per_m2 = int(price / area)

                apt = self.new_apt(
                    застройщик=dev_name,
                    название_жк=proj_name,
                    район_адрес=str(district),
                    ссылка_жк=proj_url,
                    ссылка_квартира=proj_url + f"?flat={flat.get('id', '')}",
                    комнат=flat.get("rooms") or flat.get("bedrooms"),
                    площадь_м2=area,
                    цена_полная_тг=price,
                    цена_за_м2_тг=price_per_m2,
                    этаж=flat.get("floor"),
                    дом_блок_секция=flat.get("building") or flat.get("section"),
                    срок_сдачи=str(deadline),
                    статус=flat.get("status", "доступно"),
                    отделка=flat.get("finishing") or flat.get("decoration"),
                    класс_жилья=str(housing_class),
                    условия_покупки=self._parse_terms(proj),
                )
                apartments.append(apt)
            if len(flats) < limit:
                break
            offset += limit
            self._sleep()
        return apartments

    # ---------- HTML fallback methods ----------

    def _fetch_projects_html(self) -> list[dict]:
        projects = []
        page = 1
        while True:
            url = f"{SITE_BASE}/новостройки-астаны?page={page}"
            soup = self.soup(url)
            if not soup:
                break
            cards = soup.select(".project-card, .card-project, [class*='ProjectCard'], [class*='project-item']")
            if not cards:
                break
            for card in cards:
                link_el = card.find("a", href=True)
                href = link_el["href"] if link_el else ""
                name_el = card.find(["h2", "h3", "h4", ".title", ".name"])
                projects.append({
                    "slug": href.split("/")[-1] if href else "",
                    "name": name_el.get_text(strip=True) if name_el else "",
                    "url": SITE_BASE + href if href.startswith("/") else href,
                })
            next_btn = soup.select_one("a[rel='next'], .pagination-next, [class*='next']")
            if not next_btn:
                break
            page += 1
            self._sleep()
        return projects

    def _fetch_project_html(self, proj: dict) -> list[dict]:
        if not proj.get("url"):
            return []
        soup = self.soup(proj["url"])
        if not soup:
            return []
        apartments = []
        rows = soup.select("table.flats tr, .flat-row, [class*='flat-item'], [class*='FlatRow']")
        for row in rows[1:]:
            cols = row.find_all(["td", "div"])
            if len(cols) < 4:
                continue
            texts = [c.get_text(strip=True) for c in cols]
            apt = self.new_apt(
                название_жк=proj.get("name", ""),
                ссылка_жк=proj.get("url", ""),
                комнат=safe_float(texts[0]) if texts else None,
                площадь_м2=safe_float(texts[1]) if len(texts) > 1 else None,
                цена_полная_тг=safe_price(texts[2]) if len(texts) > 2 else None,
            )
            if apt["площадь_м2"] and apt["цена_полная_тг"]:
                apt["цена_за_м2_тг"] = int(apt["цена_полная_тг"] / apt["площадь_м2"])
            apartments.append(apt)
        return apartments

    @staticmethod
    def _parse_terms(proj: dict) -> str:
        terms = []
        if proj.get("mortgage") or proj.get("has_mortgage"):
            terms.append("ипотека")
        if proj.get("installment") or proj.get("has_installment"):
            terms.append("рассрочка")
        if proj.get("discount") or proj.get("promo"):
            terms.append("скидки/акции")
        return ", ".join(terms) if terms else "уточнить у застройщика"
