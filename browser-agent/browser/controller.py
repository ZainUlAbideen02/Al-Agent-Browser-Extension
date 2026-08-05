import os
import time
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from playwright.sync_api import (
    sync_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError
)

logger = logging.getLogger("browser_agent.browser.controller")

# Default hard timeout per action step (20 seconds)
DEFAULT_TIMEOUT_MS = 20000

# Locked default viewport settings for Pure Visual Agent (1280x800)
DEFAULT_VIEWPORT_WIDTH = 1280
DEFAULT_VIEWPORT_HEIGHT = 800

class BrowserController:
    """
    Playwright controller supporting fixed 1280x800 viewport sizing, visual state captures,
    exponential backoff navigation retries, smooth mouse cursor movement, and native hardware actions.
    """

    def __init__(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        default_timeout_ms: int = DEFAULT_TIMEOUT_MS
    ):
        env_w = os.getenv("VIEWPORT_WIDTH")
        env_h = os.getenv("VIEWPORT_HEIGHT")

        if width is not None:
            self.width = int(width)
        elif env_w is not None:
            self.width = int(env_w)
        else:
            self.width = DEFAULT_VIEWPORT_WIDTH

        if height is not None:
            self.height = int(height)
        elif env_h is not None:
            self.height = int(env_h)
        else:
            self.height = DEFAULT_VIEWPORT_HEIGHT

        self.default_timeout_ms = default_timeout_ms

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser is not started. Call controller.start() first.")
        return self._page

    def start(self, headless: bool = False) -> None:
        """Launch Playwright browser session locked to 1280x800 viewport."""
        logger.info(f"Starting browser (viewport={self.width}x{self.height}, headless={headless}, timeout={self.default_timeout_ms}ms)...")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=[
                f"--window-size={self.width},{self.height}",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        self.context = self._browser.new_context(
            viewport={"width": self.width, "height": self.height},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self._page = self.context.new_page()
        self._page.set_viewport_size({"width": self.width, "height": self.height})
        self._page.set_default_timeout(self.default_timeout_ms)
        self._page.set_default_navigation_timeout(self.default_timeout_ms)
        logger.info(f"Browser session initialized locked to {self.width}x{self.height} viewport.")

    def goto(self, url: str, timeout: Optional[int] = None, max_retries: int = 3) -> None:
        """Navigate browser to specified URL with exponential backoff network retry guard (1s, 2s, 4s)."""
        timeout_ms = timeout or self.default_timeout_ms
        if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("file://"):
            url = f"https://{url}"

        delays = [1, 2, 4]
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Navigating to {url} (Attempt {attempt}/{max_retries}, timeout={timeout_ms}ms)...")
                self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                return
            except Exception as pe:
                logger.warning(f"Navigation to {url} failed on attempt {attempt}: {pe}")
                if attempt == max_retries:
                    logger.error(f"Navigation to {url} permanently failed after {max_retries} retries.")
                    raise
                backoff_sec = delays[attempt - 1] if attempt <= len(delays) else 2 ** (attempt - 1)
                logger.info(f"Retrying navigation in {backoff_sec}s...")
                time.sleep(backoff_sec)

    def get_viewport_dimensions(self) -> Tuple[int, int]:
        """Returns active viewport integer dimensions (width, height)."""
        return self.width, self.height

    def get_visual_state(self, screenshot_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Captures visual page state returning base64 screenshot image, viewport dimensions, URL, and title.
        Saves PNG file to disk if screenshot_path is provided.
        """
        page = self.page
        current_url = page.url
        page_title = page.title()

        png_bytes = page.screenshot(full_page=False)
        base64_image = base64.b64encode(png_bytes).decode("utf-8")

        if screenshot_path:
            out_path = Path(screenshot_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(png_bytes)
            logger.info(f"Saved visual state screenshot to {screenshot_path}")

        return {
            "base64_image": base64_image,
            "viewport_width": self.width,
            "viewport_height": self.height,
            "current_url": current_url,
            "page_title": page_title
        }

    # Native Mouse & Keyboard Input Methods
    def mouse_move(self, x: int, y: int, smooth: bool = True, steps: int = 5) -> None:
        """
        Move mouse cursor to specific (x, y) pixel coordinates.
        If smooth is True, uses multiple intermediate mouse.move() steps for natural motion.
        """
        logger.info(f"Mouse move to coordinates: ({x}, {y}) [smooth={smooth}]")
        num_steps = steps if smooth else 1
        self.page.mouse.move(x, y, steps=num_steps)

    def mouse_click(self, x: int, y: int, smooth: bool = True) -> None:
        """Move cursor smoothly and click at specific (x, y) page pixel coordinates."""
        logger.info(f"Mouse click at coordinates: ({x}, {y})")
        self.mouse_move(x, y, smooth=smooth)
        self.page.mouse.click(x, y)

    def mouse_scroll(self, delta_x: int = 0, delta_y: int = 500) -> None:
        """Scroll page using mouse wheel by delta_x and delta_y pixels."""
        logger.info(f"Mouse scroll wheel: delta_x={delta_x}, delta_y={delta_y}")
        self.page.mouse.wheel(delta_x, delta_y)
        self.page.wait_for_timeout(300)

    def scroll(self, dx: int = 0, dy: int = 500) -> None:
        """Native scroll method using mouse wheel."""
        self.mouse_scroll(delta_x=dx, delta_y=dy)

    def keyboard_type(self, text: str) -> None:
        """Type text string using native keyboard input."""
        logger.info(f"Keyboard typing text: '{text}'")
        self.page.keyboard.type(text)

    def key_press(self, key_name: str) -> None:
        """Press a specific keyboard key (e.g. 'Enter', 'Tab', 'Escape', 'Backspace')."""
        logger.info(f"Keyboard pressing key: '{key_name}'")
        self.page.keyboard.press(key_name)

    def keyboard_press(self, key: str) -> None:
        """Alias matching key_press."""
        self.key_press(key)

    # Legacy DOM Helper Methods (retained for DOM/hybrid modes)
    def click_coordinate(self, x: int, y: int) -> None:
        """Legacy helper matching mouse_click(x, y)."""
        self.mouse_click(x, y)

    def _resolve_locator(self, selector: str, timeout_ms: int):
        """Try resolving selector with standard CSS or text fallback."""
        locator = self.page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except PlaywrightTimeoutError:
            if ":has-text(" in selector:
                try:
                    clean_text = None
                    if ':has-text("' in selector:
                        clean_text = selector.split(':has-text("')[1].rstrip('")')
                    elif ":has-text('" in selector:
                        clean_text = selector.split(":has-text('")[1].rstrip("')")

                    if clean_text:
                        alt_locator = self.page.get_by_text(clean_text, exact=False).first
                        alt_locator.wait_for(state="visible", timeout=timeout_ms // 2)
                        return alt_locator
                except Exception:
                    pass
            raise

    def click(self, selector: str, timeout: Optional[int] = None) -> None:
        """Click an element matching selector with stale element retry."""
        timeout_ms = timeout or self.default_timeout_ms
        logger.info(f"Clicking selector: '{selector}'")
        locator = self._resolve_locator(selector, timeout_ms)
        locator.click(timeout=timeout_ms)

    def type_text(self, selector: str, text: str, timeout: Optional[int] = None, press_enter: bool = False) -> None:
        """Focus an element and fill text."""
        timeout_ms = timeout or self.default_timeout_ms
        logger.info(f"Typing '{text}' into selector: '{selector}'")
        locator = self._resolve_locator(selector, timeout_ms)
        locator.click(timeout=timeout_ms // 2)
        locator.fill(text)
        if press_enter:
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
            self.context = None
            self._browser = None
            self._playwright = None
