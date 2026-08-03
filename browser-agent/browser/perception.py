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
            rect.top >= -500 && rect.left >= -500 &&
            rect.top <= (window.innerHeight + 500) &&
            rect.left <= (window.innerWidth + 500) &&
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            style.opacity !== '0'
        );
    }

    function buildSelector(el) {
        if (el.id) {
            return `#${CSS.escape(el.id)}`;
        }
        if (el.getAttribute('name')) {
            return `${el.tagName.toLowerCase()}[name="${el.getAttribute('name')}"]`;
        }
        if (el.getAttribute('aria-label')) {
            return `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
        }
        if (el.getAttribute('placeholder')) {
            return `${el.tagName.toLowerCase()}[placeholder="${el.getAttribute('placeholder')}"]`;
        }
        if (el.getAttribute('role')) {
            const role = el.getAttribute('role');
            const text = (el.innerText || el.textContent || '').trim().slice(0, 20);
            if (text) {
                return `[role="${role}"]:has-text("${text.replace(/"/g, '\\"')}")`;
            }
            return `[role="${role}"]`;
        }
        
        const text = (el.innerText || el.textContent || el.value || '').trim();
        if (text && text.length > 0 && text.length <= 40) {
            const cleanText = text.replace(/[\n\r]+/g, ' ').replace(/"/g, '\\"');
            return `${el.tagName.toLowerCase()}:has-text("${cleanText}")`;
        }

        let path = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\s+/).filter(c => c && !c.includes(':')).slice(0, 2);
            if (classes.length > 0) {
                path += '.' + classes.map(c => CSS.escape(c)).join('.');
            }
        }
        return path;
    }

    for (const el of elements) {
        if (!isVisible(el)) continue;

        const tag = el.tagName.toLowerCase();
        const text = (el.innerText || el.textContent || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 80);
        const selector = buildSelector(el);

        let optionsList = [];
        if (tag === 'select' && el.options) {
            optionsList = Array.from(el.options).map(o => ({
                value: o.value || '',
                text: (o.text || '').trim()
            })).filter(o => o.text.length > 0);
        }

        if (!seenSelectors.has(selector)) {
            seenSelectors.add(selector);
            results.push({
                tag: tag,
                text: text,
                type: el.getAttribute('type') || '',
                placeholder: el.getAttribute('placeholder') || '',
                aria_label: el.getAttribute('aria-label') || '',
                selector: selector,
                options: optionsList
            });
        }

        if (results.length >= 30) break;
    }

    return results;
}
"""

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
    url = page.url
    title = page.title()

    screenshot_filename = f"step_{step_num}.png"
    screenshot_path = os.path.join(log_dir, screenshot_filename)
    controller.screenshot(screenshot_path)

    try:
        elements: List[Dict[str, Any]] = page.evaluate(EXTRACTION_JS)
    except Exception as e:
        logger.warning(f"DOM extraction script failed: {e}. Falling back to empty element list.")
        elements = []

    logger.info(f"Page State [Step {step_num}]: Title='{title}' | Elements Found={len(elements)}")

    return {
        "url": url,
        "title": title,
        "elements": elements,
        "screenshot_path": screenshot_path
    }
