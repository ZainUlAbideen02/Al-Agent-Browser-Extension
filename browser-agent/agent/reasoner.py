import logging
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, ValidationError
from agent.base_agent import BaseAgent

logger = logging.getLogger("browser_agent.agent.reasoner")

class ActionDecision(BaseModel):
    """Pydantic schema for structured action decision output from LLM."""
    action: Literal["click", "click_coordinate", "type", "select", "scroll", "wait", "done"] = Field(
        description="The action type to perform. Must be one of: click, click_coordinate, type, select, scroll, wait, done."
    )
    selector: Optional[str] = Field(
        default=None,
        description="Playwright selector or CSS locator for the target interactive element."
    )
    x: Optional[int] = Field(
        default=None,
        description="Optional X pixel coordinate for visual click on canvas or non-DOM element."
    )
    y: Optional[int] = Field(
        default=None,
        description="Optional Y pixel coordinate for visual click on canvas or non-DOM element."
    )
    text: Optional[str] = Field(
        default=None,
        description="Text content to type into input field (required if action is 'type')."
    )
    value: Optional[str] = Field(
        default=None,
        description="Option text label or value string to select from native <select> dropdown (required if action is 'select')."
    )
    reasoning: str = Field(
        description="Step-by-step reasoning explaining why this action was chosen."
    )

SYSTEM_PROMPT_DOM = """You are an AI web automation agent. Your goal is to complete a user task on a web page by taking one step at a time.

Available Actions:
1. "click": Click an interactive element specified by its 'selector' (use for buttons, links, non-native custom dropdowns).
2. "click_coordinate": Click at specific (x, y) pixel coordinates (specify integer 'x' and 'y' fields).
3. "type": Focus an element specified by its 'selector' and type the specified 'text'.
4. "select": Choose an option from a native HTML <select> element by specifying its 'selector' and option label/value in 'value' (e.g. selector: "#dropdown", value: "Option 2").
5. "scroll": Scroll the page down or up (selector can be "down" or "up").
6. "wait": Pause briefly (2 seconds) to allow dynamic contents or search results to load.
7. "done": Declare that the objective has been successfully completed.

Rules:
- For native HTML <select> dropdown elements, ALWAYS use the "select" action with the target option label/value in 'value'. Do NOT try to click options inside a select dropdown.
- Use the exact 'selector' provided for the target element.
- If the goal is satisfied, choose "done".
- Output strictly valid JSON matching this schema:
{
  "action": "click" | "click_coordinate" | "type" | "select" | "scroll" | "wait" | "done",
  "selector": "<exact locator string or null>",
  "x": null,
  "y": null,
  "text": "<text to enter if action is type else null>",
  "value": "<option value/label to choose if action is select else null>",
  "reasoning": "<short sentence explaining why>"
}
- Do NOT wrap in markdown text outside the JSON block.
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
            options = el.get("options", [])

            details = f"[{i}] <{tag}>"
            if text:
                details += f" text='{text}'"
            if placeholder:
                details += f" placeholder='{placeholder}'"
            if el_type:
                details += f" type='{el_type}'"
            if options:
                opt_str = ", ".join([f"'{o.get('text')}'" for o in options])
                details += f" | Available Select Options: [{opt_str}]"
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
        Multimodal Vision Fallback: Prompt Gemini/Groq vision model with page screenshot when DOM selector fails.
        """
        screenshot_path = page_state.get("screenshot_path")
        logger.info(f"Triggering Vision Fallback using screenshot: {screenshot_path}")

        elements: List[Dict[str, Any]] = page_state.get("elements", [])
        elements_str = self._format_elements(elements)

        system_prompt = f"""You are an AI web automation vision expert.
A previous DOM-based interaction failed on this webpage. You are provided with the current webpage screenshot image to visually analyze the layout.

Task Goal: "{goal}"
Action Failure Reason: "{failure_reason}"

Your Objective:
Examine the visual screenshot of the page carefully.
1. Identify the target element visually (e.g., look for buttons, canvas elements, links, or text).
2. If the target element has a clear CSS selector in DOM (e.g. '#canvasB'), specify "action": "click" and "selector": "#canvasB".
3. If the element is drawn inside a canvas or lacks a valid DOM selector, output "action": "click_coordinate" with integer pixel coordinates 'x' and 'y' (e.g. x: 160, y: 55).
4. Output strictly valid JSON matching this schema:
{{
  "action": "click" or "click_coordinate",
  "selector": "#canvasB" or null,
  "x": 160 or null,
  "y": 55 or null,
  "text": null,
  "value": null,
  "reasoning": "<short explanation based on visual analysis of the screenshot>"
}}
Do NOT output extra text outside the JSON object.
"""
        user_message = f"""Page URL: {page_state.get('url', 'N/A')}
Page Title: {page_state.get('title', 'N/A')}

DOM Elements Context:
{elements_str}

Recent Action History:
{history_summary}

Please analyze the attached screenshot image and recommend the corrected action decision JSON.
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
                logger.info(f"Vision Fallback Decision: {result.get('action')} | Selector: {result.get('selector')} | X: {result.get('x')} | Y: {result.get('y')}")
                return result
            except ValidationError as ve:
                logger.warning(f"Vision decision validation error (attempt {attempt + 1}): {ve}")
                if attempt == max_retries:
                    raise RuntimeError(f"Vision decision validation failed: {ve}") from ve
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Please output valid JSON matching fields: action, selector, x, y, text, value, reasoning.]"
            except Exception as e:
                logger.error(f"Vision Fallback failed: {e}")
                raise

        raise RuntimeError("Failed to generate valid Vision decision.")
