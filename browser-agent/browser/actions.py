import time
import logging
from typing import Dict, Any
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from browser.controller import BrowserController

logger = logging.getLogger("browser_agent.browser.actions")

def execute_action(
    controller: BrowserController,
    action_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Executes action dictionary safely with structured error outputs and stale element recovery.

    Args:
        controller: Active BrowserController instance.
        action_dict: Action specification from LLM (action, selector, text, reasoning).

    Returns:
        Dict containing success (bool), error_type (str), message (str), and stale_element (bool).
    """
    action_type = action_dict.get("action")
    selector = action_dict.get("selector")
    text = action_dict.get("text")
    reasoning = action_dict.get("reasoning", "")

    logger.info(f"Executing Action: '{action_type}' | Selector: '{selector}' | Text: '{text}'")

    try:
        if action_type == "click":
            if not selector:
                return {
                    "success": False,
                    "error_type": "missing_selector",
                    "message": "Click action requires a valid 'selector'.",
                    "stale_element": False
                }
            try:
                controller.click(selector)
            except PlaywrightTimeoutError:
                # Stale-element / re-fetch attempt: wait 1 second and retry click once
                logger.warning(f"Click selector '{selector}' timed out. Re-attempting locator check...")
                time.sleep(1)
                controller.click(selector, timeout=5000)

            time.sleep(1)
            return {
                "success": True,
                "error_type": None,
                "message": f"Successfully clicked '{selector}'.",
                "stale_element": False
            }

        elif action_type == "type":
            if not selector:
                return {
                    "success": False,
                    "error_type": "missing_selector",
                    "message": "Type action requires a valid 'selector'.",
                    "stale_element": False
                }
            if text is None:
                text = ""
            try:
                controller.type_text(selector, text)
            except PlaywrightTimeoutError:
                logger.warning(f"Type selector '{selector}' timed out. Re-attempting locator check...")
                time.sleep(1)
                controller.type_text(selector, text, timeout=5000)

            time.sleep(1)
            return {
                "success": True,
                "error_type": None,
                "message": f"Successfully typed '{text}' into '{selector}'.",
                "stale_element": False
            }

        elif action_type == "scroll":
            direction = selector if selector in ("up", "down") else "down"
            controller.scroll(direction=direction)
            return {
                "success": True,
                "error_type": None,
                "message": f"Successfully scrolled page {direction}.",
                "stale_element": False
            }

        elif action_type == "wait":
            time.sleep(2)
            return {
                "success": True,
                "error_type": None,
                "message": "Waited 2 seconds for page update.",
                "stale_element": False
            }

        elif action_type == "done":
            return {
                "success": True,
                "error_type": None,
                "message": f"Task completed by agent: {reasoning}",
                "stale_element": False
            }

        else:
            return {
                "success": False,
                "error_type": "unknown_action",
                "message": f"Unknown action type '{action_type}'.",
                "stale_element": False
            }

    except PlaywrightTimeoutError as te:
        logger.error(f"Playwright Timeout Error on selector '{selector}': {te}")
        return {
            "success": False,
            "error_type": "selector_timeout",
            "message": f"Element '{selector}' was not found or not interactable within timeout.",
            "stale_element": True
        }

    except PlaywrightError as pe:
        logger.error(f"Playwright Error on selector '{selector}': {pe}")
        return {
            "success": False,
            "error_type": "playwright_error",
            "message": f"Playwright error interacting with '{selector}': {pe}",
            "stale_element": True
        }

    except Exception as e:
        logger.error(f"Unexpected error executing action '{action_type}': {e}")
        return {
            "success": False,
            "error_type": "unexpected_error",
            "message": f"Failed with exception: {e}",
            "stale_element": False
        }
