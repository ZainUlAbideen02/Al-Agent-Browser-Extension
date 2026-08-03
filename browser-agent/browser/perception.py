import os
import logging
from typing import Dict, Any, List
from browser.controller import BrowserController

logger = logging.getLogger("browser_agent.browser.perception")

# JavaScript snippet to extract interactive elements with robust selectors and select options
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
        
        // Use text locators if available for links and buttons
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

        // Fallback: nth-of-type relative to parent
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

        if (results.length >= 30) break; // Limit to 30 elements for token efficiency
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
