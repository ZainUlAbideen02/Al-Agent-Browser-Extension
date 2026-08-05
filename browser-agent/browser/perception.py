import os
import io
import base64
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont
from browser.controller import BrowserController

logger = logging.getLogger("browser_agent.browser.perception")

_CACHED_GRID_OVERLAY: Optional[Image.Image] = None

def get_precomputed_grid_overlay(width: int = 1280, height: int = 800, grid_step: int = 100) -> Image.Image:
    """
    Precomputes and caches the 100px red grounding grid overlay RGBA image.
    Avoids re-drawing lines and text labels on every single screenshot capture step.
    """
    global _CACHED_GRID_OVERLAY
    if _CACHED_GRID_OVERLAY is not None and _CACHED_GRID_OVERLAY.size == (width, height):
        return _CACHED_GRID_OVERLAY

    overlay = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    line_color = (255, 50, 50, 100)       # Light red semi-transparent gridline
    text_color = (255, 255, 255, 240)    # White coordinate text
    bg_box_color = (15, 23, 42, 180)     # Dark slate semi-transparent text background pill

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # Draw vertical grid lines
    for x in range(0, width, grid_step):
        draw.line([(x, 0), (x, height)], fill=line_color, width=1)

    # Draw horizontal grid lines
    for y in range(0, height, grid_step):
        draw.line([(0, y), (width, y)], fill=line_color, width=1)

    # Draw intersection coordinate labels (e.g. "100,200")
    for x in range(0, width, grid_step):
        for y in range(0, height, grid_step):
            label_text = f"{x},{y}"
            tx = x + 3
            ty = y + 3
            text_w = len(label_text) * 6
            text_h = 10
            draw.rectangle([(tx - 1, ty - 1), (tx + text_w + 1, ty + text_h + 1)], fill=bg_box_color)
            draw.text((tx, ty), label_text, fill=text_color, font=font)

    _CACHED_GRID_OVERLAY = overlay
    return _CACHED_GRID_OVERLAY

def annotate_screenshot(
    image_input: Union[str, bytes],
    out_path: Optional[str] = None,
    grid_step: int = 100
) -> Tuple[str, str]:
    """
    Composites precomputed coordinate reference grid on screenshot image.
    Returns tuple of (base64_png_string, output_filepath).
    """
    if isinstance(image_input, (str, Path)):
        img = Image.open(image_input).convert("RGB")
    else:
        img = Image.open(io.BytesIO(image_input)).convert("RGB")

    width, height = img.size
    overlay = get_precomputed_grid_overlay(width=width, height=height, grid_step=grid_step)
    annotated_img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    if out_path:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        annotated_img.save(out_p, format="PNG")
        logger.info(f"Saved annotated grid screenshot to {out_path}")

    buf = io.BytesIO()
    annotated_img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")

    return b64_str, out_path or ""

def capture_visual_state(
    controller: BrowserController,
    screenshot_path: Optional[str] = None,
    grid_overlay: bool = True
) -> Dict[str, Any]:
    """
    Captures visual page state at 1280x800.
    If grid_overlay is True, composites cached 100px reference gridlines on screenshot.
    """
    state = controller.get_visual_state(screenshot_path=screenshot_path)
    state["screenshot_path"] = screenshot_path

    if grid_overlay and screenshot_path and Path(screenshot_path).exists():
        try:
            annotated_b64, _ = annotate_screenshot(
                image_input=screenshot_path,
                out_path=screenshot_path,
                grid_step=100
            )
            state["base64_image"] = annotated_b64
        except Exception as e:
            logger.warning(f"Failed to apply grid overlay to screenshot: {e}")

    return state

# JavaScript snippet to extract interactive elements for legacy DOM / Hybrid mode
EXTRACTION_JS = r"""
() => {
    const interactiveSelectors = [
        'a[href]', 'button', 'input', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[role="searchbox"]', '[role="textbox"]',
        '[role="tab"]', '[role="menuitem"]', '[onclick]'
    ];

    const elements = Array.from(document.querySelectorAll(interactiveSelectors.join(',')));
    const results = [];
    const seenSelectors = new Set();

    function isVisible(el) {
        if (!el) return false;
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            style.opacity !== '0'
        );
    }

    function buildSelector(el) {
        if (el.id) {
            const escapedId = CSS.escape ? CSS.escape(el.id) : el.id;
            return `#${escapedId}`;
        }

        const tag = el.tagName.toLowerCase();
        
        const text = (el.innerText || el.textContent || '').trim();
        if (text && text.length <= 40 && (tag === 'a' || tag === 'button')) {
            const cleanText = text.replace(/"/g, '\\"').replace(/\n/g, ' ');
            return `${tag}:has-text("${cleanText}")`;
        }

        if (el.name) {
            return `${tag}[name="${el.name}"]`;
        }
        if (el.placeholder) {
            return `${tag}[placeholder="${el.placeholder}"]`;
        }
        if (el.getAttribute('role')) {
            return `${tag}[role="${el.getAttribute('role')}"]`;
        }

        const parent = el.parentElement;
        if (parent) {
            const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
            if (siblings.length > 1) {
                const index = siblings.indexOf(el) + 1;
                return `${tag}:nth-of-type(${index})`;
            }
        }

        return tag;
    }

    for (const el of elements) {
        if (!isVisible(el)) continue;

        const tag = el.tagName.toLowerCase();
        const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 50);
        const selector = buildSelector(el);
        
        if (seenSelectors.has(selector)) continue;
        seenSelectors.add(selector);

        let options = [];
        if (tag === 'select') {
            options = Array.from(el.options).map(opt => ({
                value: opt.value,
                text: (opt.text || opt.innerText || '').trim()
            }));
        }

        results.push({
            tag: tag,
            text: text,
            selector: selector,
            type: el.type || null,
            placeholder: el.placeholder || null,
            options: options
        });

        if (results.length >= 30) break;
    }

    return results;
}
"""

class DOMPerception:
    """Class wrapper around perception DOM extraction script."""

    def extract_state(self, page, screenshot_path: str) -> Dict[str, Any]:
        """Extract simplified DOM state and save screenshot."""
        url = page.url
        title = page.title()
        try:
            page.screenshot(path=screenshot_path, full_page=False)
        except Exception as se:
            logger.warning(f"Screenshot capture failed: {se}")

        try:
            elements: List[Dict[str, Any]] = page.evaluate(EXTRACTION_JS)
        except Exception as e:
            logger.warning(f"DOM extraction script failed: {e}. Falling back to empty element list.")
            elements = []

        return {
            "url": url,
            "title": title,
            "elements": elements,
            "screenshot_path": screenshot_path
        }

def get_page_state(
    controller: BrowserController,
    step_num: int,
    log_dir: str = "logs"
) -> Dict[str, Any]:
    """
    Extract simplified DOM (interactive elements + select options), page metadata, and capture a step screenshot.
    """
    os.makedirs(log_dir, exist_ok=True)
    page = controller.page
    screenshot_path = os.path.join(log_dir, f"step_{step_num}.png")
    return DOMPerception().extract_state(page, screenshot_path)
