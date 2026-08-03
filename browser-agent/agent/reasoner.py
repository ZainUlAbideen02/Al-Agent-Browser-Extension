import logging
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, ValidationError
from agent.base_agent import BaseAgent

logger = logging.getLogger("browser_agent.agent.reasoner")

class ActionDecision(BaseModel):
    """Pydantic schema for structured action decision output from LLM."""
    action: Literal["click", "type", "scroll", "wait", "done"] = Field(
        description="The action type to perform. Must be one of: click, type, scroll, wait, done."
    )
    selector: Optional[str] = Field(
        default=None,
        description="Playwright selector or CSS locator for the target interactive element."
    )
    text: Optional[str] = Field(
        default=None,
        description="Text content to type into input field (required if action is 'type')."
    )
    reasoning: str = Field(
        description="Step-by-step reasoning explaining why this action was chosen."
    )

SYSTEM_PROMPT_DOM = """You are an AI web automation agent. Your goal is to complete a user task on a web page by taking one step at a time.

Available Actions:
1. "click": Click an interactive element specified by its 'selector'.
2. "type": Focus an element specified by its 'selector' and type the specified 'text'.
3. "scroll": Scroll the page down or up (selector can be "down" or "up").
4. "wait": Pause briefly (2 seconds) to allow dynamic contents or search results to load.
5. "done": Declare that the objective has been successfully completed.

Rules:
- Choose from the list of visible interactive elements provided. Use the exact 'selector' provided for the target element.
- If the goal is satisfied (e.g. search result visible or task completed), choose "done".
- Always output strictly valid JSON matching this schema:
{
  "action": "click" | "type" | "scroll" | "wait" | "done",
  "selector": "<exact locator string or null>",
  "text": "<text to enter if action is type else null>",
  "reasoning": "<short sentence explaining why>"
}
- Do NOT wrap in markdown text outside the JSON block.
"""

SYSTEM_PROMPT_VISION = """You are an AI web automation vision expert.
A previous DOM-based interaction failed on this webpage. You are provided with the current webpage screenshot image to visually analyze the layout.

Task Goal: "{goal}"
Action Failure Reason: "{failure_reason}"

Your Objective:
Examine the visual screenshot of the page carefully.
1. Identify the target element visually (e.g., search bar, link, button, input).
2. Propose an alternative, resilient selector (e.g., text locator `text="Search"`, ID `#search`, `input[type="text"]`, or alternative button) or a recovery action (`scroll`, `wait`).
3. Output strictly valid JSON matching:
{
  "action": "click" | "type" | "scroll" | "wait" | "done",
  "selector": "<alternative locator string or null>",
  "text": "<text to enter if type action else null>",
  "reasoning": "<explanation based on visual screenshot analysis>"
}
"""

class ReasonerAgent(BaseAgent):
    """LLM Reasoner agent deciding next action using DOM perception or Vision Fallback."""

    def _format_elements(self, elements: List[Dict[str, Any]]) -> str:
        formatted = []
        for i, el in enumerate(elements, 1):
            tag = el.get("tag", "")
            text = el.get("text", "")
            selector = el.get("selector", "")
            el_type = el.get("type", "")
            placeholder = el.get("placeholder", "")

            details = f"[{i}] <{tag}>"
            if text:
                details += f" text='{text}'"
            if placeholder:
                details += f" placeholder='{placeholder}'"
            if el_type:
                details += f" type='{el_type}'"
            details += f" | Selector: `{selector}`"
            formatted.append(details)
        return "\n".join(formatted) if formatted else "No interactive elements detected."

    def decide_next_action(
        self,
        goal: str,
        page_state: Dict[str, Any],
        history_summary: str
    ) -> Dict[str, Any]:
        """
        Evaluate current state using DOM data and return validated action decision.
        """
        elements: List[Dict[str, Any]] = page_state.get("elements", [])
        elements_str = self._format_elements(elements)

        user_message = f"""Current Goal: "{goal}"

Current Page URL: {page_state.get('url', 'N/A')}
Current Page Title: {page_state.get('title', 'N/A')}

Interactive Elements on Page (~{len(elements)} items):
{elements_str}

Action History (Recent steps):
{history_summary}

Analyze the current page state, goal, and past actions. What is the single next best action to take?
Respond strictly in JSON format.
"""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                raw_decision = self.call_llm(
                    system_prompt=SYSTEM_PROMPT_DOM,
                    user_message=user_message,
                    expect_json=True
                )
                decision_obj = ActionDecision(**raw_decision)
                return decision_obj.model_dump()
            except ValidationError as ve:
                logger.warning(f"Pydantic DOM validation failed (attempt {attempt + 1}): {ve}")
                if attempt == max_retries:
                    raise RuntimeError(f"Action decision failed validation: {ve}") from ve
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Please fix JSON format.]"
            except Exception as e:
                logger.error(f"Error deciding action via DOM: {e}")
                raise

        raise RuntimeError("Failed to generate valid DOM action decision.")

    def decide_with_vision(
        self,
        goal: str,
        page_state: Dict[str, Any],
        history_summary: str,
        failure_reason: str
    ) -> Dict[str, Any]:
        """
        Multimodal Vision Fallback: Prompt Gemini with page screenshot when DOM selector fails.
        """
        screenshot_path = page_state.get("screenshot_path")
        logger.info(f"Triggering Vision Fallback using screenshot: {screenshot_path}")

        elements: List[Dict[str, Any]] = page_state.get("elements", [])
        elements_str = self._format_elements(elements)

        system_prompt = SYSTEM_PROMPT_VISION.format(goal=goal, failure_reason=failure_reason)
        user_message = f"""Page URL: {page_state.get('url', 'N/A')}
Page Title: {page_state.get('title', 'N/A')}

DOM Elements Context:
{elements_str}

Recent Action History:
{history_summary}

Please analyze the attached screenshot and recommend a corrected action decision JSON.
"""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                raw_decision = self.call_llm(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    expect_json=True,
                    image_path=screenshot_path
                )
                decision_obj = ActionDecision(**raw_decision)
                result = decision_obj.model_dump()
                logger.info(f"Vision Fallback Decision: {result.get('action')} | Selector: {result.get('selector')}")
                return result
            except ValidationError as ve:
                logger.warning(f"Vision decision validation error (attempt {attempt + 1}): {ve}")
                if attempt == max_retries:
                    raise RuntimeError(f"Vision decision validation failed: {ve}") from ve
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Please fix JSON format.]"
            except Exception as e:
                logger.error(f"Vision Fallback failed: {e}")
                raise

        raise RuntimeError("Failed to generate valid Vision decision.")
