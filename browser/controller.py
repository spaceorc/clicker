"""Playwright browser controller for automated navigation."""

import asyncio
import base64
import io
import logging
from dataclasses import dataclass

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


class BrowserController:
    """Playwright wrapper for browser automation."""

    __slots__ = ("_browser", "_context", "_headless", "_page", "_playwright", "_viewport", "_user_data_dir")

    def __init__(self, viewport: ViewportSize | None = None, headless: bool = True, user_data_dir: str | None = None) -> None:
        self._viewport = viewport or ViewportSize()
        self._headless = headless
        self._user_data_dir = user_data_dir
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def viewport(self) -> ViewportSize:
        return self._viewport

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def start(self) -> None:
        """Launch browser and create a page."""
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
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            logger.info("Browser started with persistent context (headless=%s, viewport=%dx%d)",
                       self._headless, self._viewport.width, self._viewport.height)
        else:
            # Standard mode - fresh session every time
            self._browser = await pw.chromium.launch(headless=self._headless)
            self._context = await self._browser.new_context(
                viewport={"width": self._viewport.width, "height": self._viewport.height},
            )
            self._page = await self._context.new_page()
            logger.info("Browser started (headless=%s, viewport=%dx%d)",
                       self._headless, self._viewport.width, self._viewport.height)

    async def stop(self) -> None:
        """Close browser and cleanup."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
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
