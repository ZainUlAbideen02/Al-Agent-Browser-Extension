import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("browser_agent.agent.memory")

class StepMemory:
    """Tracks step history and guards against endless execution loops."""

    def __init__(self, max_history: int = 10):
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
        """Record step entry in history with vision usage tracking."""
        if used_vision_fallback:
            self.vision_fallback_count += 1

        if not result.get("success", False):
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0

        entry = {
            "step_num": step_num,
            "action_taken": action_taken,
            "result": result,
            "screenshot_path": screenshot_path,
            "used_vision_fallback": used_vision_fallback,
            "page_url": page_state.get("url", ""),
            "page_title": page_state.get("title", "")
        }
        self.history.append(entry)
        logger.info(f"Recorded Step {step_num}: Action={action_taken.get('action')} | Success={result.get('success')} | VisionFallback={used_vision_fallback}")

    def should_trigger_vision_fallback(self) -> bool:
        """Trigger vision fallback if action execution failed 2 consecutive times."""
        return self.consecutive_failures >= 2

    def is_looping(self, window: int = 3) -> bool:
        """
        Detects if the agent is stuck performing duplicate actions on static URL/Title.
        Ignores 'wait' actions unless 5 or more consecutive identical wait actions occur.
        """
        if len(self.history) < window:
            return False

        recent = self.history[-window:]
        actions = [s["action_taken"].get("action") for s in recent]
        selectors = [s["action_taken"].get("action_type", s["action_taken"].get("selector")) for s in recent]
        urls = [s.get("page_url") for s in recent]
        titles = [s.get("page_title") for s in recent]

        # Ignore wait actions unless at least 5 consecutive waits occur
        if all(act == "wait" for act in actions):
            if len(self.history) < 5:
                return False
            five_recent = [s["action_taken"].get("action") for s in self.history[-5:]]
            return all(act == "wait" for act in five_recent)

        # Check if same action & selector executed repeatedly with static URL and Title
        same_action = len(set(actions)) == 1
        same_selector = len(set(selectors)) == 1
        same_url = len(set(urls)) == 1
        same_title = len(set(titles)) == 1

        if same_action and same_selector and same_url and same_title:
            logger.warning(
                f"Loop Guard Triggered: Action {actions[0]} on '{selectors[0]}' repeated {window} times "
                f"with zero page progress (URL: {urls[0]}). Agent is stuck."
            )
            return True

        return False

    def get_summary(self, max_recent: int = 5) -> str:
        """Returns string summary of last N steps for prompt context."""
        if not self.history:
            return "No previous steps taken."

        recent_steps = self.history[-max_recent:]
        formatted = []
        for s in recent_steps:
            act = s["action_taken"]
            res = s["result"]
            status = "SUCCESS" if res.get("success") else f"FAILED ({res.get('message')})"
            vis_tag = " [Vision Fallback Used]" if s.get("used_vision_fallback") else ""
            line = f"Step {s['step_num']}: Action='{act.get('action')}' (Selector='{act.get('selector')}', Text='{act.get('text')}') -> Status: {status}{vis_tag}"
            formatted.append(line)

        return "\n".join(formatted)
