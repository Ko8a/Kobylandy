"""Base scraper class with shared utilities."""

import logging
import time
import random
import requests
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

EMPTY_APARTMENT = {
    "застройщик": None,
    "название_жк": None,
    "город": "Астана",
    "район_адрес": None,
    "ссылка_жк": None,
    "ссылка_квартира": None,
    "комнат": None,
    "площадь_м2": None,
    "цена_полная_тг": None,
    "цена_за_м2_тг": None,
    "этаж": None,
    "дом_блок_секция": None,
    "срок_сдачи": None,
    "статус": None,
    "отделка": None,
    "класс_жилья": None,
    "условия_покупки": None,
    "дата_парсинга": None,
    "источник": None,
}


class BaseScraper:
    """Base class for all scrapers."""

    SOURCE_NAME = "unknown"
    BASE_URL = ""

    def __init__(self, delay_min: float = 1.0, delay_max: float = 3.0):
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._rotate_ua()

    def _rotate_ua(self):
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)

    def _sleep(self):
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"[{self.SOURCE_NAME}] sleeping {delay:.1f}s")
        time.sleep(delay)

    def get(self, url: str, timeout: int = 15, **kwargs) -> Optional[requests.Response]:
        self._rotate_ua()
        try:
            resp = self.session.get(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            logger.debug(f"[{self.SOURCE_NAME}] GET {url} -> {resp.status_code}")
            return resp
        except requests.exceptions.HTTPError as e:
            logger.warning(f"[{self.SOURCE_NAME}] HTTP error {url}: {e}")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"[{self.SOURCE_NAME}] Connection error {url}: {e}")
        except requests.exceptions.Timeout:
            logger.warning(f"[{self.SOURCE_NAME}] Timeout {url}")
        except Exception as e:
            logger.error(f"[{self.SOURCE_NAME}] Unexpected error {url}: {e}")
        return None

    def soup(self, url: str, **kwargs) -> Optional[BeautifulSoup]:
        resp = self.get(url, **kwargs)
        if resp:
            return BeautifulSoup(resp.text, "lxml")
        return None

    def now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def new_apt(self, **kwargs) -> dict:
        apt = dict(EMPTY_APARTMENT)
        apt["дата_парсинга"] = self.now()
        apt["источник"] = self.SOURCE_NAME
        apt.update(kwargs)
        return apt

    def scrape(self) -> list[dict]:
        raise NotImplementedError


def safe_price(value: str) -> Optional[int]:
    """Parse price string to integer tenge."""
    if not value:
        return None
    cleaned = "".join(c for c in str(value) if c.isdigit())
    return int(cleaned) if cleaned else None


def safe_float(value: str) -> Optional[float]:
    """Parse area string to float."""
    if not value:
        return None
    cleaned = str(value).replace(",", ".").replace(" ", "")
    cleaned = "".join(c for c in cleaned if c.isdigit() or c == ".")
    try:
        return float(cleaned)
    except ValueError:
        return None
