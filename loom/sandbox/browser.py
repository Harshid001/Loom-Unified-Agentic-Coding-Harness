"""
Loom Playwright Browser Controller & Web Sandbox Integration.
Allows Loom agents to autonomously control browsers, capture screenshots,
interact with web dashboard UIs, and perform E2E web verification.
"""

from pathlib import Path
from typing import Any, Dict, Optional

try:
    from playwright.async_api import async_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class LoomBrowserRunner:
    """Async Playwright browser integration for Loom agents."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._page: Optional[Any] = None

    async def start(self) -> None:
        """Launch browser instance."""
        if not _HAS_PLAYWRIGHT:
            raise RuntimeError(
                "playwright package is not installed. Run: pip install playwright && playwright install chromium"
            )
        playwright_obj = await async_playwright().start()
        self._playwright = playwright_obj
        self._browser = await playwright_obj.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page(viewport={"width": 1280, "height": 800})

    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to URL and return page title & status."""
        if not self._page:
            await self.start()
        assert self._page is not None
        response = await self._page.goto(url, wait_until="domcontentloaded")
        title = await self._page.title()
        status = response.status if response else 200
        return {"url": url, "title": title, "status": status}

    async def click(self, selector: str) -> None:
        """Click an element by CSS selector or text matcher."""
        if not self._page:
            raise RuntimeError("Browser session not started.")
        await self._page.click(selector)

    async def fill(self, selector: str, text: str) -> None:
        """Fill an input field."""
        if not self._page:
            raise RuntimeError("Browser session not started.")
        await self._page.fill(selector, text)

    async def take_screenshot(self, output_path: str) -> str:
        """Capture screenshot and save to path."""
        if not self._page:
            raise RuntimeError("Browser session not started.")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._page.screenshot(path=str(path), full_page=True)
        return str(path)

    async def get_text(self, selector: str) -> str:
        """Extract inner text from element."""
        if not self._page:
            return ""
        element = await self._page.query_selector(selector)
        return await element.inner_text() if element else ""

    async def close(self) -> None:
        """Close browser session."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._page = None
        self._playwright = None
