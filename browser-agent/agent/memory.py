import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("browser_agent.agent.memory")

class StepMemory:
    """Tracks step history, vision fallback flags, and detects repetitive loops with progress tracking."""

    def __init__(self):
        self.history: List[Dict[str, Any]] = []

    def add_step(
        self,
        step_num: int,
        action_taken: Dict[str, Any],
        result: Dict[str, Any],
        screenshot_path: Optional[str] = None,
        used_vision_fallback: bool = False,
        page_url: str = "",
        page_title: str = ""
    ) -> None:
        """Record step entry in history with vision fallback flag and page state snapshot."""
        entry = {
            "step_num": step_num,
            "action_taken": action_taken,
            "result": result,
            "screenshot_path": screenshot_path,
            "used_vision_fallback": used_vision_fallback,
            "page_url": page_url,
            "page_title": page_title
        }
        self.history.append(entry)
        logger.info(
            f"Recorded Step {step_num}: Action={action_taken.get('action')} | "
            f"Success={result.get('success')} | VisionFallback={used_vision_fallback}"
        )

    def format_history(self, max_steps: int = 5) -> str:
        """Format the last `max_steps` items into a concise string for LLM prompts."""
        if not self.history:
            return "No previous actions taken yet."

        recent_steps = self.history[-max_steps:]
        formatted_lines = []

        for step in recent_steps:
            num = step["step_num"]
            act = step["action_taken"]
            res = step["result"]
            vision_flag = " (via Vision Fallback)" if step.get("used_vision_fallback") else ""

            action_type = act.get("action", "unknown")
            selector = act.get("selector", "")
            text = act.get("text", "")
            reasoning = act.get("reasoning", "")
            status = "SUCCESS" if res.get("success") else f"FAILED ({res.get('message', 'error')})"

            desc = f"Step {num}: Action '{action_type}'{vision_flag}"
            if selector:
                desc += f" on '{selector}'"
            if text:
                desc += f" with text '{text}'"
            desc += f" -> Status: {status}. Reason: {reasoning}"
            formatted_lines.append(desc)

        return "\n".join(formatted_lines)

    def is_looping(self, repeat_threshold: int = 3) -> Dict[str, Any]:
        """
        Check if the last `repeat_threshold` steps performed identical actions
        without making progress (page URL and title unchanged).

        Returns:
            Dict: {"is_looping": bool, "reason": str}
        """
        if len(self.history) < repeat_threshold:
            return {"is_looping": False, "reason": ""}

        recent_window = self.history[-repeat_threshold:]

        # Extract (action, selector, text) tuples
        action_tuples = [
            (
                s["action_taken"].get("action"),
                s["action_taken"].get("selector"),
                s["action_taken"].get("text")
            )
            for s in recent_window
        ]

        first_action = action_tuples[0]
        if first_action[0] in ("done", None):
            return {"is_looping": False, "reason": ""}

        # Check if all action tuples in recent window are identical
        all_actions_identical = all(act == first_action for act in action_tuples)

        # Check if page URL and page title remained static
        urls = [s.get("page_url", "") for s in recent_window]
        titles = [s.get("page_title", "") for s in recent_window]
        no_progress = (len(set(urls)) == 1) and (len(set(titles)) == 1)

        if all_actions_identical and no_progress:
            msg = (
                f"Action {first_action[0]} on '{first_action[1]}' repeated {repeat_threshold} times "
                f"with zero page progress (URL: {urls[0]}). Agent is stuck."
            )
            logger.warning(f"Loop Guard Triggered: {msg}")
            return {"is_looping": True, "reason": msg}

        return {"is_looping": False, "reason": ""}

    def get_vision_fallback_count(self) -> int:
        """Return total count of steps that required Vision Fallback."""
        return sum(1 for step in self.history if step.get("used_vision_fallback"))

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        total = len(self.history)
        vision_count = self.get_vision_fallback_count()
        pure_dom_count = total - vision_count
        return {
            "total_steps": total,
            "pure_dom_steps": pure_dom_count,
            "vision_fallback_steps": vision_count,
            "vision_fallback_ratio": round(vision_count / total, 2) if total > 0 else 0.0
        }
