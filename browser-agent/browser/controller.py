import time
import logging
from typing import Optional
from playwright.sync_api import sync_playwright, Playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

logger = logging.getLogger("browser_agent.browser.controller")

# Default hard timeout per action step (20 seconds)
DEFAULT_TIMEOUT_MS = 20000

class BrowserController:
    """Synchronous Playwright wrapper with per-step hard timeouts and robust locator recovery."""

    def __init__(self, default_timeout_ms: int = DEFAULT_TIMEOUT_MS):
        self.default_timeout_ms = default_timeout_ms
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser is not started. Call controller.start() first.")
        return self._page

    def start(self, headless: bool = False) -> None:
        """Launch Playwright browser session."""
        logger.info(f"Starting browser (headless={headless}, timeout={self.default_timeout_ms}ms)...")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self._page = context.new_page()
        self._page.set_default_timeout(self.default_timeout_ms)
        self._page.set_default_navigation_timeout(self.default_timeout_ms)
        logger.info("Browser session initialized.")

    def goto(self, url: str, timeout: Optional[int] = None, max_retries: int = 3) -> None:
        """Navigate browser to specified URL with exponential backoff network retry guard."""
        timeout_ms = timeout or self.default_timeout_ms
        if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("file://"):
            url = f"https://{url}"

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Navigating to {url} (Attempt {attempt}/{max_retries}, timeout={timeout_ms}ms)...")
                self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                return
            except PlaywrightError as pe:
                logger.warning(f"Navigation to {url} failed on attempt {attempt}: {pe}")
                if attempt == max_retries:
                    raise
                backoff_sec = 2 ** attempt
                logger.info(f"Retrying navigation in {backoff_sec} seconds...")
                time.sleep(backoff_sec)

    def _resolve_locator(self, selector: str, timeout_ms: int):
        """Try resolving selector with standard CSS or text fallback."""
        locator = self.page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except PlaywrightTimeoutError:
            if ":has-text(" in selector:
                clean_text = selector.split(':has-text("')[1].rstrip('")')
                alt_locator = self.page.get_by_text(clean_text, exact=False).first
                alt_locator.wait_for(state="visible", timeout=timeout_ms // 2)
                return alt_locator
            raise

    def click(self, selector: str, timeout: Optional[int] = None) -> None:
        """Click an element matching selector with stale element retry."""
        timeout_ms = timeout or self.default_timeout_ms
        logger.info(f"Clicking selector: '{selector}'")
        locator = self._resolve_locator(selector, timeout_ms)
        locator.click(timeout=timeout_ms)

    def click_coordinate(self, x: int, y: int) -> None:
        """Click at specific (x, y) page coordinates."""
        logger.info(f"Clicking at pixel coordinates: ({x}, {y})")
        self.page.mouse.click(x, y)

    def type_text(self, selector: str, text: str, timeout: Optional[int] = None) -> None:
        """Focus an element, type text, and press Enter."""
        timeout_ms = timeout or self.default_timeout_ms
        logger.info(f"Typing '{text}' into selector: '{selector}'")
        locator = self._resolve_locator(selector, timeout_ms)
        locator.click(timeout=timeout_ms // 2)
        locator.fill(text)
        self.page.keyboard.press("Enter")

    def select_option(self, selector: str, value: str, timeout: Optional[int] = None) -> None:
        """Select an option in a native <select> dropdown by label or value."""
        timeout_ms = timeout or self.default_timeout_ms
        logger.info(f"Selecting option '{value}' in dropdown selector: '{selector}'")
        locator = self._resolve_locator(selector, timeout_ms)
        try:
            locator.select_option(label=value, timeout=timeout_ms)
        except Exception:
            locator.select_option(value=value, timeout=timeout_ms)

    def scroll(self, direction: str = "down", amount: int = 500) -> None:
        """Scroll page vertically."""
        logger.info(f"Scrolling {direction} by {amount}px...")
        delta_y = amount if direction.lower() == "down" else -amount
        self.page.mouse.wheel(0, delta_y)
        self.page.wait_for_timeout(1000)

    def screenshot(self, save_path: str) -> str:
        """Capture screenshot and save to PNG path."""
        logger.info(f"Saving screenshot to {save_path}...")
        self.page.screenshot(path=save_path, full_page=False)
        return save_path

    def close(self) -> None:
        """Close browser context and stop Playwright."""
        logger.info("Closing browser...")
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error during browser closure: {e}")
        finally:
            self._page = None
            self._browser = None
            self._playwright = None
