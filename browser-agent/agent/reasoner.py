import logging
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, ValidationError
from agent.base_agent import BaseAgent

logger = logging.getLogger("browser_agent.agent.reasoner")

class VisualActionDecision(BaseModel):
    """Pydantic schema for Pure Visual Computer-Use Agent action decision."""
    thought: str = Field(
        default="Analyzing visual screenshot context.",
        description="Detailed visual analysis of the screenshot, identifying buttons, input fields, dropdowns, or canvas elements."
    )
    action: Literal["click", "type", "key", "scroll", "drag_and_drop", "wait", "done"] = Field(
        ...,
        description="The physical action to execute on the browser."
    )
    x: Optional[int] = Field(None, description="Exact center X pixel coordinate of the target element.")
    y: Optional[int] = Field(None, description="Exact center Y pixel coordinate of the target element.")
    text: Optional[str] = Field(None, description="Text string to type, or key name to press (e.g., 'Enter', 'Tab').")
    direction: Optional[Literal["up", "down", "left", "right"]] = Field(None, description="Scroll direction.")
    start_x: Optional[int] = Field(None, description="Drag start X coordinate.")
    start_y: Optional[int] = Field(None, description="Drag start Y coordinate.")
    end_x: Optional[int] = Field(None, description="Drag end X coordinate.")
    end_y: Optional[int] = Field(None, description="Drag end Y coordinate.")

class ActionDecision(BaseModel):
    """Schema supporting DOM perception and fallback calls."""
    action: Literal["click", "click_coordinate", "type", "select", "scroll", "wait", "done"] = Field(
        ...,
        description="The action type to perform. Must be one of: click, click_coordinate, type, select, scroll, wait, done."
    )
    selector: Optional[str] = Field(default=None)
    x: Optional[int] = Field(default=None)
    y: Optional[int] = Field(default=None)
    text: Optional[str] = Field(default=None)
    value: Optional[str] = Field(default=None)
    reasoning: Optional[str] = Field(default="Executing next action step.")

SYSTEM_PROMPT_VISUAL = """You are a visual computer-use agent controlling a web browser strictly via screenshots.
Current Active Viewport: {viewport_width}px wide x {viewport_height}px high.

INSTRUCTIONS:
1. Analyze the screenshot to locate visual targets.
2. Identify visual bounding boxes of elements (buttons, inputs, dropdowns, canvas items).
3. Calculate the center (X, Y) pixel coordinates strictly within 0..{max_x} (X) and 0..{max_y} (Y).
4. FORM FILLING PROCEDURE:
   - To fill an input box: specify 'click' or 'type' with the field's center (X,Y) coordinates.
   - Include the text to type in the 'text' key.
   - Follow up with 'key' -> 'Tab' to move to the next field, or 'key' -> 'Enter' to submit.
5. If popups/ads block the target, click the 'X' button or click outside the modal.
6. Output strictly valid JSON matching the schema:
{{
  "thought": "<detailed visual analysis of the screenshot identifying target buttons, inputs, text>",
  "action": "click" | "type" | "key" | "scroll" | "drag_and_drop" | "wait" | "done",
  "x": 640 or null,
  "y": 400 or null,
  "text": "text string or key name" or null,
  "direction": "down" or null,
  "start_x": null,
  "start_y": null,
  "end_x": null,
  "end_y": null
}}
Do NOT output any markdown formatting or extra text outside the JSON object.
"""

SYSTEM_PROMPT_DOM = """You are an AI web automation agent. Your goal is to complete a user task on a web page by taking one step at a time.

Available Actions:
1. "click": Click an interactive element specified by its 'selector' (use for buttons, links, login submit buttons).
2. "click_coordinate": Click at specific (x, y) pixel coordinates.
3. "type": Focus an element specified by its 'selector' and type the specified 'text'.
4. "select": Choose an option from a native HTML <select> element.
5. "scroll": Scroll page down or up.
6. "wait": Pause 2 seconds.
7. "done": Declare completion.

Rules:
- For multi-step forms: Once you type into a field (e.g. #username or #password), DO NOT type into that same field again. Immediately click the submit/Login button (`button[type="submit"]` or `button.radius` or `button:has-text("Login")`).
- If the current page URL or title indicates success (e.g. page redirected to /secure or logged in or target reached), output "done".
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
"""

class ReasonerAgent(BaseAgent):
    """LLM Reasoner agent supporting Pure Visual Computer-Use and Hybrid DOM reasoning."""

    def decide_visual_action(
        self,
        goal: str,
        visual_state: Dict[str, Any],
        history_summary: str
    ) -> Dict[str, Any]:
        """
        Pure Visual Computer-Use Agent reasoning: Analyzes page screenshot and viewport metadata to decide visual action.
        """
        vw = visual_state.get("viewport_width", 1280)
        vh = visual_state.get("viewport_height", 800)
        max_x = vw - 1
        max_y = vh - 1
        screenshot_path = visual_state.get("screenshot_path")

        system_prompt = SYSTEM_PROMPT_VISUAL.format(
            viewport_width=vw,
            viewport_height=vh,
            max_x=max_x,
            max_y=max_y
        )

        user_message = f"""User Goal: "{goal}"

Current Page URL: {visual_state.get('current_url', 'N/A')}
Current Page Title: {visual_state.get('page_title', 'N/A')}
Viewport Dimensions: {vw}x{vh} pixels

Execution History (Last 5 steps):
{history_summary}

Analyze the attached screenshot carefully. Determine the exact next visual action to execute.
Output strictly valid JSON matching the schema.
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
                decision_obj = VisualActionDecision(**raw_decision)
                result = decision_obj.model_dump()
                result["reasoning"] = result.get("thought", "")
                logger.info(f"Visual Decision: Action={result['action']} | Coords=({result.get('x')}, {result.get('y')}) | Thought: {result['thought'][:60]}...")
                return result
            except ValidationError as ve:
                logger.warning(f"Pydantic Visual validation failed (attempt {attempt + 1}): {ve}")
                if attempt == max_retries:
                    raise RuntimeError(f"Visual action decision failed validation: {ve}") from ve
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Please output valid JSON matching fields: thought, action, x, y, text, direction.]"
            except Exception as e:
                logger.error(f"Error deciding visual action: {e}")
                raise

        raise RuntimeError("Failed to generate valid visual action decision.")

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
        """Evaluate current state using DOM data and return validated action decision."""
        elements: List[Dict[str, Any]] = page_state.get("elements", [])
        elements_str = self._format_elements(elements)

        user_message = f"""Current Goal: "{goal}"

Current Page URL: {page_state.get('url', 'N/A')}
Current Page Title: {page_state.get('title', 'N/A')}

Interactive Elements on Page (~{len(elements)} items):
{elements_str}

Action History (Recent steps):
{history_summary}

Analyze the current page state, goal, and past actions. Choose action from: "click", "click_coordinate", "type", "select", "scroll", "wait", "done".
Output strictly valid JSON with keys: "action", "selector", "x", "y", "text", "value", "reasoning".
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
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Please fix JSON output format with fields: action, selector, reasoning.]"
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
        """Multimodal Vision Fallback: Prompt vision model with page screenshot when DOM selector fails."""
        screenshot_path = page_state.get("screenshot_path")
        logger.info(f"Triggering Vision Fallback using screenshot: {screenshot_path}")

        visual_state = {
            "viewport_width": 1280,
            "viewport_height": 800,
            "current_url": page_state.get("url", ""),
            "page_title": page_state.get("title", ""),
            "screenshot_path": screenshot_path
        }
        return self.decide_visual_action(goal=goal, visual_state=visual_state, history_summary=history_summary)
