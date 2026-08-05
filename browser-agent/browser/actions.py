import time
import logging
from typing import Dict, Any, Tuple, Optional
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from browser.controller import BrowserController

logger = logging.getLogger("browser_agent.browser.actions")

def validate_and_clamp_coordinates(
    x: int,
    y: int,
    viewport_w: int = 1280,
    viewport_h: int = 800
) -> Tuple[int, int, bool]:
    """
    Validates and clamps pixel coordinates within active viewport boundaries [0, viewport_w - 1] x [0, viewport_h - 1].
    Logs a warning-level flag 'low_confidence_prediction' whenever clamping is needed.
    Returns tuple: (clamped_x, clamped_y, is_low_confidence).
    """
    clamped_x = max(0, min(int(x), viewport_w - 1))
    clamped_y = max(0, min(int(y), viewport_h - 1))
    is_low_confidence = (clamped_x != x or clamped_y != y)

    if is_low_confidence:
        logger.warning(
            f"low_confidence_prediction: Coordinate out of bounds warning! "
            f"Predicted ({x}, {y}) clamped to ({clamped_x}, {clamped_y}) for viewport ({viewport_w}x{viewport_h})."
        )

    return clamped_x, clamped_y, is_low_confidence

def execute_visual_action(
    controller: BrowserController,
    action_data: Dict[str, Any]
) -> Tuple[bool, str, bool]:
    """
    Translates pure visual AI coordinate decisions into direct Playwright mouse and keyboard hardware commands.
    No CSS selectors used in pure visual mode.
    Returns tuple: (success_bool, message_str, low_confidence_prediction_bool).
    """
    action_type = action_data.get("action")
    reasoning = action_data.get("reasoning", action_data.get("thought", ""))
    viewport_w, viewport_h = controller.get_viewport_dimensions()
    is_low_confidence = False

    try:
        if action_type in ("click", "click_coordinate"):
            x = action_data.get("x")
            y = action_data.get("y")

            if x is None or y is None:
                selector = action_data.get("selector")
                if selector:
                    controller.click(selector)
                    return True, f"Clicked selector '{selector}'", False
                return False, "Click action requires 'x' and 'y' pixel coordinates.", False

            cx, cy, is_low_confidence = validate_and_clamp_coordinates(x, y, viewport_w, viewport_h)
            controller.mouse_click(cx, cy, smooth=True)
            time.sleep(0.5)
            msg = f"Clicked at ({cx}, {cy})" + (" [low_confidence_prediction]" if is_low_confidence else "")
            return True, msg, is_low_confidence

        elif action_type == "type":
            text = action_data.get("text", "")
            x = action_data.get("x")
            y = action_data.get("y")
            selector = action_data.get("selector")

            if x is not None and y is not None:
                cx, cy, is_low_confidence = validate_and_clamp_coordinates(x, y, viewport_w, viewport_h)
                controller.mouse_click(cx, cy, smooth=True)
                time.sleep(0.2)
                # Clear existing field value with Ctrl+A -> Backspace
                controller.key_press("Control+a")
                controller.key_press("Backspace")
                time.sleep(0.1)
                controller.keyboard_type(text)
                time.sleep(0.5)
                msg = f"Typed '{text}' at ({cx}, {cy})" + (" [low_confidence_prediction]" if is_low_confidence else "")
                return True, msg, is_low_confidence
            elif selector:
                controller.type_text(selector, text)
                time.sleep(0.5)
                return True, f"Typed '{text}' into selector '{selector}'", False
            else:
                controller.keyboard_type(text)
                time.sleep(0.5)
                return True, f"Typed '{text}'", False

        elif action_type in ("key", "keyboard_press"):
            key_name = action_data.get("key") or action_data.get("text") or action_data.get("value", "Enter")
            controller.key_press(key_name)
            time.sleep(0.5)
            return True, f"Pressed key '{key_name}'", False

        elif action_type == "scroll":
            direction = str(action_data.get("direction") or action_data.get("selector") or "down").lower()
            amount = int(action_data.get("amount", 500))

            delta_x, delta_y = 0, 0
            if direction == "down":
                delta_y = amount
            elif direction == "up":
                delta_y = -amount
            elif direction == "right":
                delta_x = amount
            elif direction == "left":
                delta_x = -amount
            else:
                delta_y = amount

            controller.scroll(dx=delta_x, dy=delta_y)
            return True, f"Scrolled {direction} by {amount}px", False

        elif action_type == "drag_and_drop":
            start_x = action_data.get("start_x", 0)
            start_y = action_data.get("start_y", 0)
            end_x = action_data.get("end_x", 0)
            end_y = action_data.get("end_y", 0)

            cs_x, cs_y, lc1 = validate_and_clamp_coordinates(start_x, start_y, viewport_w, viewport_h)
            ce_x, ce_y, lc2 = validate_and_clamp_coordinates(end_x, end_y, viewport_w, viewport_h)
            is_low_confidence = lc1 or lc2

            controller.mouse_move(cs_x, cs_y, smooth=True)
            controller.page.mouse.down()
            controller.mouse_move(ce_x, ce_y, smooth=True)
            controller.page.mouse.up()
            time.sleep(0.5)
            return True, f"Dragged from ({cs_x}, {cs_y}) to ({ce_x}, {ce_y})", is_low_confidence

        elif action_type == "select":
            selector = action_data.get("selector")
            value = action_data.get("value") or action_data.get("text") or ""
            if selector:
                controller.select_option(selector, value)
                return True, f"Selected option '{value}' in '{selector}'", False
            return False, "Select action requires a selector.", False

        elif action_type == "wait":
            time.sleep(2.0)
            return True, "Waited 2 seconds for page load.", False

        elif action_type == "done":
            return True, f"Task completed by agent: {reasoning}", False

        else:
            return False, f"Unknown action type '{action_type}'", False

    except PlaywrightTimeoutError as te:
        logger.error(f"Playwright Timeout Error during action '{action_type}': {te}")
        return False, f"Action '{action_type}' timed out.", False

    except PlaywrightError as pe:
        logger.error(f"Playwright Error during action '{action_type}': {pe}")
        return False, f"Playwright error during action '{action_type}': {pe}", False

    except Exception as e:
        logger.error(f"Unexpected error executing action '{action_type}': {e}")
        return False, f"Execution exception: {e}", False

def execute_action(
    controller: BrowserController,
    action_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Legacy wrapper maintaining backward compatibility for existing code callers.
    Returns structured dictionary.
    """
    success, message, low_confidence = execute_visual_action(controller, action_dict)
    return {
        "success": success,
        "error_type": None if success else "execution_error",
        "message": message,
        "stale_element": False,
        "low_confidence_prediction": low_confidence
    }
