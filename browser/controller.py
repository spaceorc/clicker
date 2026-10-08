"""Playwright browser controller for automated navigation."""

import asyncio
import base64
import io
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

_GRID_STEP = 100
_GRID_COLOR = (255, 0, 0, 80)
_LABEL_COLOR = (255, 0, 0, 180)


def _draw_grid(screenshot_bytes: bytes, width: int, height: int) -> bytes:
    """Draw a coordinate grid overlay on a screenshot."""
    img = Image.open(io.BytesIO(screenshot_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11)
    except OSError:
        font = ImageFont.load_default()

    # Vertical lines + x labels
    for x in range(_GRID_STEP, width, _GRID_STEP):
        draw.line([(x, 0), (x, height)], fill=_GRID_COLOR, width=1)
        draw.text((x + 2, 2), str(x), fill=_LABEL_COLOR, font=font)

    # Horizontal lines + y labels
    for y in range(_GRID_STEP, height, _GRID_STEP):
        draw.line([(0, y), (width, y)], fill=_GRID_COLOR, width=1)
        draw.text((2, y + 2), str(y), fill=_LABEL_COLOR, font=font)

    img = Image.alpha_composite(img, overlay)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


@dataclass(frozen=True, slots=True)
class ViewportSize:
    """Browser viewport dimensions."""

    width: int = 1280
    height: int = 720


@dataclass(frozen=True, slots=True)
class PageInfo:
    """Open browser page (tab, popup or window)."""

    id: int
    url: str
    title: str
    active: bool


class BrowserController:
    """Playwright wrapper for browser automation."""

    __slots__ = ("_browser", "_context", "_headless", "_next_page_id", "_page", "_pages", "_playwright", "_viewport", "_user_data_dir")

    def __init__(self, viewport: ViewportSize | None = None, headless: bool = True, user_data_dir: str | None = None) -> None:
        self._viewport = viewport or ViewportSize()
        self._headless = headless
        self._user_data_dir = user_data_dir
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._pages: dict[int, Page] = {}  # open pages by stable id, in opening order
        self._next_page_id = 1

    @property
    def viewport(self) -> ViewportSize:
        return self._viewport

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def _ensure_browsers_installed(self) -> None:
        """Check if Playwright browsers are installed, install if needed."""
        # Check if chromium browser is already installed
        # Playwright stores browsers in ~/.cache/ms-playwright on Linux/Mac
        playwright_cache = Path.home() / ".cache" / "ms-playwright"
        chromium_installed = any(
            (playwright_cache / d).exists()
            for d in ["chromium-*", "webkit-*"]
            if (playwright_cache).exists() and list(playwright_cache.glob(d))
        )

        if not chromium_installed:
            logger.info("Installing Playwright browsers (first run)...")
            print("📥 Installing Playwright browsers (first run, this may take a minute)...")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logger.info("Playwright browsers installed successfully")
                print("✅ Browsers installed successfully")
            except subprocess.CalledProcessError as e:
                logger.error("Failed to install Playwright browsers: %s", e.stderr)
                raise RuntimeError(f"Failed to install Playwright browsers: {e.stderr}")

    async def start(self) -> None:
        """Launch browser and create a page."""
        # Check if Chromium is installed, install if needed (first run)
        await self._ensure_browsers_installed()

        pw = await async_playwright().start()
        self._playwright = pw

        if self._user_data_dir:
            # Use persistent context to save cookies and session data
            logger.info("Using persistent context: %s", self._user_data_dir)
            self._context = await pw.chromium.launch_persistent_context(
                user_data_dir=self._user_data_dir,
                headless=self._headless,
                viewport={"width": self._viewport.width, "height": self._viewport.height},
            )
            self._context.on("page", lambda page: self._track_page(page))
            for page in self._context.pages:
                self._track_page(page)
            if not self._pages:
                self._track_page(await self._context.new_page())
            logger.info("Browser started with persistent context (headless=%s, viewport=%dx%d)",
                       self._headless, self._viewport.width, self._viewport.height)
        else:
            # Standard mode - fresh session every time
            self._browser = await pw.chromium.launch(headless=self._headless)
            self._context = await self._browser.new_context(
                viewport={"width": self._viewport.width, "height": self._viewport.height},
            )
            self._context.on("page", lambda page: self._track_page(page))
            self._track_page(await self._context.new_page())
            logger.info("Browser started (headless=%s, viewport=%dx%d)",
                       self._headless, self._viewport.width, self._viewport.height)

    def _track_page(self, page: Page) -> None:
        """Register an open page (popup, new tab or window). The active page stays the same."""
        if page in self._pages.values():
            return
        page_id = self._next_page_id
        self._next_page_id += 1
        self._pages[page_id] = page
        page.on("close", lambda: self._on_page_closed(page_id))
        if self._page is None:
            self._page = page
        else:
            logger.info("New page %d opened: %s", page_id, page.url)

    def _on_page_closed(self, page_id: int) -> None:
        page = self._pages.pop(page_id, None)
        if page is not None and self._page is page:
            self._page = next(reversed(self._pages.values()), None)
            logger.info("Active page %d closed, switched to: %s", page_id, self._page.url if self._page else None)

    async def list_pages(self) -> list[PageInfo]:
        """List open pages with their ids, titles and URLs."""
        result: list[PageInfo] = []
        for page_id, page in self._pages.items():
            try:
                title = await page.title()
            except Exception:
                title = ""
            result.append(PageInfo(id=page_id, url=page.url, title=title, active=page is self._page))
        return result

    async def switch_page(self, page_id: int) -> None:
        """Make the page with the given id active."""
        page = self._pages.get(page_id)
        if page is None:
            raise ValueError(f"No open page with id {page_id}")
        logger.info("Switching to page %d: %s", page_id, page.url)
        self._page = page
        await page.bring_to_front()

    async def stop(self) -> None:
        """Close browser and cleanup."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._pages = {}
        self._context = None
        self._browser = None
        self._playwright = None
        logger.info("Browser stopped")

    async def navigate(self, url: str) -> None:
        """Navigate to URL and wait for load."""
        logger.info("Navigating to %s", url)
        await self.page.goto(url, wait_until="load")

    async def screenshot_base64(self) -> str:
        """Take a viewport screenshot with coordinate grid overlay, return as base64 PNG."""
        screenshot_bytes = await self.page.screenshot(scale="css")
        screenshot_bytes = _draw_grid(screenshot_bytes, self._viewport.width, self._viewport.height)
        return base64.b64encode(screenshot_bytes).decode("ascii")

    async def click(self, x: int, y: int) -> None:
        """Click at coordinates."""
        logger.info("Click at (%d, %d)", x, y)
        await self.page.mouse.click(x, y)

    async def double_click(self, x: int, y: int) -> None:
        """Double-click at coordinates."""
        logger.info("Double-click at (%d, %d)", x, y)
        await self.page.mouse.dblclick(x, y)

    async def drag(self, from_x: int, from_y: int, to_x: int, to_y: int) -> None:
        """Drag from one position to another."""
        logger.info("Drag from (%d, %d) to (%d, %d)", from_x, from_y, to_x, to_y)
        await self.page.mouse.move(from_x, from_y)
        await self.page.mouse.down()
        await self.page.mouse.move(to_x, to_y, steps=20)
        await self.page.mouse.up()

    async def type_text(self, text: str) -> None:
        """Type text into the currently focused element."""
        logger.info("Typing text: %s", text[:50])
        await self.page.keyboard.type(text)

    async def press_key(self, key: str) -> None:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        logger.info("Pressing key: %s", key)
        await self.page.keyboard.press(key)

    async def scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> None:
        """Scroll at a given position."""
        logger.info("Scroll at (%d, %d) delta=(%d, %d)", x, y, delta_x, delta_y)
        await self.page.mouse.move(x, y)
        await self.page.mouse.wheel(delta_x, delta_y)

    async def wait(self, ms: int) -> None:
        """Wait for a specified duration in milliseconds."""
        logger.info("Waiting %d ms", ms)
        await asyncio.sleep(ms / 1000.0)

    async def current_url(self) -> str:
        """Get the current page URL."""
        return self.page.url
