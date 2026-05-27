"""
Playwright-based scraper helper for JavaScript-heavy sites.

Use this when running from a residential IP (home internet).
Sites requiring Playwright: sensata.kz, bi.group, gbg.kz, ramsqz.com.

Usage:
    from scrapers.playwright_helper import PlaywrightSession
    async with PlaywrightSession() as session:
        html = await session.get_html("https://bi.group/ru/special/kvartiry-v-astane")
        api_data = await session.intercept_api("https://bi.group/...", api_pattern="/api/")
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-extensions",
    "--no-first-run",
    "--disable-default-apps",
]

VIEWPORT = {"width": 1440, "height": 900}

LOCALE = "ru-RU"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class PlaywrightSession:
    """
    Async context manager for Playwright sessions.

    Example:
        async with PlaywrightSession() as pw:
            html = await pw.get_html("https://bi.group/...")
            # or intercept API:
            data = await pw.intercept_json("https://bi.group/...", "/api/")
    """

    def __init__(self, headless: bool = True, delay: float = 2.0):
        self.headless = headless
        self.delay = delay
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().__aenter__()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=CHROMIUM_ARGS,
        )
        self._context = await self._browser.new_context(
            viewport=VIEWPORT,
            locale=LOCALE,
            user_agent=USER_AGENT,
            ignore_https_errors=True,
        )
        # Stealth: remove navigator.webdriver
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        return self

    async def __aexit__(self, *args):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.__aexit__(*args)

    async def get_html(self, url: str, wait_selector: str = None, timeout: int = 30_000) -> Optional[str]:
        """Navigate to URL and return rendered HTML."""
        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=timeout)
            await page.wait_for_timeout(int(self.delay * 1000))
            return await page.content()
        except Exception as e:
            logger.warning(f"[playwright] get_html failed for {url}: {e}")
            return None
        finally:
            await page.close()

    async def intercept_json(self, url: str, api_pattern: str, timeout: int = 30_000) -> list[dict]:
        """
        Navigate to page, intercept XHR/fetch responses matching api_pattern.
        Returns list of parsed JSON bodies.
        """
        page = await self._context.new_page()
        captured = []

        async def handle_response(response):
            if api_pattern in response.url and response.status == 200:
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        body = await response.json()
                        captured.append(body)
                        logger.debug(f"[playwright] captured API: {response.url}")
                except Exception:
                    pass

        page.on("response", handle_response)
        try:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            await page.wait_for_timeout(int(self.delay * 1000))
            # Scroll to trigger lazy loads
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
        except Exception as e:
            logger.warning(f"[playwright] intercept_json failed for {url}: {e}")
        finally:
            await page.close()
        return captured

    async def scroll_and_collect(self, url: str, card_selector: str,
                                  max_scrolls: int = 10, timeout: int = 30_000) -> list[str]:
        """
        Scroll through infinite-scroll page and collect card HTML.
        Returns list of outer HTML strings for each matching element.
        """
        page = await self._context.new_page()
        seen_cards: set[str] = set()
        results = []
        try:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            for _ in range(max_scrolls):
                cards = await page.query_selector_all(card_selector)
                for card in cards:
                    html = await card.inner_html()
                    if html not in seen_cards:
                        seen_cards.add(html)
                        results.append(html)
                prev = len(seen_cards)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                cards_after = await page.query_selector_all(card_selector)
                if len(cards_after) == prev:
                    break
        except Exception as e:
            logger.warning(f"[playwright] scroll_and_collect failed: {e}")
        finally:
            await page.close()
        return results


def run_playwright_scraper(url: str, api_pattern: str = "/api/") -> list[dict]:
    """Synchronous wrapper for use from non-async code."""
    async def _run():
        async with PlaywrightSession() as pw:
            return await pw.intercept_json(url, api_pattern)
    return asyncio.run(_run())
