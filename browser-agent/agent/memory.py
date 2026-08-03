import math
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("browser_agent.agent.memory")

class StepMemory:
    """Tracks step execution metrics, formats LLM prompt history, and detects visual spatial repetition loops."""

    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self.history: List[Dict[str, Any]] = []
        self.consecutive_failures: int = 0
        self.vision_fallback_count: int = 0

    def record_step(
        self,
        step_num: int,
        action_taken: Dict[str, Any],
        result: Dict[str, Any],
        screenshot_path: str,
        page_state: Dict[str, Any],
        used_vision_fallback: bool = False
    ) -> None:
        """Record step entry with spatial metrics and page metadata."""
        if used_vision_fallback:
            self.vision_fallback_count += 1

        if not result.get("success", False):
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0

        action_type = action_taken.get("action", "")
        selector = action_taken.get("selector")
        x = action_taken.get("x")
        y = action_taken.get("y")
        text = action_taken.get("text") or action_taken.get("value")
        reasoning = action_taken.get("thought") or action_taken.get("reasoning", "")
        url = page_state.get("url") or page_state.get("current_url", "")
        title = page_state.get("title") or page_state.get("page_title", "")

        entry = {
            "step_num": step_num,
            "action_taken": action_taken,
            "action_type": action_type,
            "selector": selector,
            "x": x,
            "y": y,
            "text": text,
            "reasoning": reasoning,
            "result": result,
            "screenshot_path": screenshot_path,
            "used_vision_fallback": used_vision_fallback,
            "page_url": url,
            "page_title": title
        }
        self.history.append(entry)
        logger.info(f"Recorded Step {step_num}: Action={action_type} | Selector={selector} | Coords=({x}, {y}) | Success={result.get('success')}")

    def should_trigger_vision_fallback(self) -> bool:
        """Trigger vision fallback if action execution failed 2 consecutive times."""
        return self.consecutive_failures >= 2

    def is_visually_stuck(self, threshold: int = 3, radius: float = 10.0) -> bool:
        """
        Detects if the agent is performing repetitive visual actions at near-identical coordinates 
        within radius pixels on the same page URL.
        Excludes legitimate 'wait' and 'scroll' actions.
        """
        if len(self.history) < threshold:
            return False

        recent = self.history[-threshold:]
        actions = [s.get("action_type") for s in recent]

        if any(act in ("wait", "scroll") for act in actions):
            return False

        urls = [s.get("page_url") for s in recent]
        if len(set(urls)) > 1:
            return False

        if len(set(actions)) != 1:
            return False

        coords = [(s.get("x"), s.get("y")) for s in recent]
        if any(c[0] is None or c[1] is None for c in coords):
            return False

        base_x, base_y = coords[0]
        for cx, cy in coords[1:]:
            dist = math.hypot(cx - base_x, cy - base_y)
            if dist > radius:
                return False

        logger.warning(
            f"Visual Loop Detected: Action '{actions[0]}' at ({base_x}, {base_y}) repeated {threshold} times "
            f"within {radius}px radius on {urls[0]}."
        )
        return True

    def get_recovery_warning(self, threshold: int = 3, radius: float = 10.0) -> Optional[str]:
        """Returns recovery warning prompt context string if visual loop is detected."""
        if self.is_visually_stuck(threshold=threshold, radius=radius):
            last_step = self.history[-1]
            act = last_step.get("action_type", "click")
            x = last_step.get("x", 0)
            y = last_step.get("y", 0)
            return (
                f"RECOVERY WARNING: Action '{act}' at ({x}, {y}) repeated {threshold} times with no visual page change. "
                f"Try scrolling, pressing Enter/Tab, or clicking a different visual element."
            )
        return None

    def get_formatted_history(self, limit: int = 5) -> str:
        """Formats the last `limit` steps into a concise string context for the LLM prompt."""
        if not self.history:
            return "No previous steps taken."

        recent_steps = self.history[-limit:]
        formatted = []
        for s in recent_steps:
            act = s.get("action_type", "")
            sel = s.get("selector")
            x = s.get("x")
            y = s.get("y")
            txt = s.get("text")

            details = []
            if sel:
                details.append(f"Selector='{sel}'")
            if x is not None and y is not None:
                details.append(f"Coords=({x}, {y})")
            if txt:
                details.append(f"Value='{txt}'")

            details_str = f" ({', '.join(details)})" if details else ""
            res = s.get("result", {})
            status = "SUCCESS" if res.get("success") else f"FAILED ({res.get('message')})"
            vis_tag = " [Vision Used]" if s.get("used_vision_fallback") else ""
            line = f"Step {s['step_num']}: Action='{act}'{details_str} -> Status: {status}{vis_tag}"
            formatted.append(line)

        warning = self.get_recovery_warning()
        if warning:
            formatted.append(f"\n⚠️ {warning}")

        return "\n".join(formatted)

    def is_looping(self, window: int = 3) -> bool:
        """Legacy helper alias matching is_visually_stuck."""
        return self.is_visually_stuck(threshold=window)

    def get_summary(self, max_recent: int = 5) -> str:
        """Legacy helper matching get_formatted_history."""
        return self.get_formatted_history(limit=max_recent)
