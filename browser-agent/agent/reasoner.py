import logging
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, ValidationError
from agent.base_agent import BaseAgent

logger = logging.getLogger("browser_agent.agent.reasoner")

class VisualActionDecision(BaseModel):
    """Pydantic schema for Pure Visual Computer-Use Agent action decision."""
    thought: str = Field(
        ...,
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
    """Legacy schema supporting DOM perception and fallback calls."""
    action: Literal["click", "click_coordinate", "type", "select", "scroll", "wait", "done"] = Field(
        description="The action type to perform."
    )
    selector: Optional[str] = Field(default=None)
    x: Optional[int] = Field(default=None)
    y: Optional[int] = Field(default=None)
    text: Optional[str] = Field(default=None)
    value: Optional[str] = Field(default=None)
    reasoning: str = Field(description="Reasoning explaining why this action was chosen.")

SYSTEM_PROMPT_VISUAL = """You are an expert AI Visual Computer-Use Agent.
You control a web browser purely by observing high-resolution page screenshots and issuing physical mouse and keyboard actions.

Active Browser Viewport: {viewport_width} x {viewport_height} pixels.

Coordinate Rules:
- All (x, y) coordinates must be integers within [0, {max_x}] for X and [0, {max_y}] for Y.
- Coordinates represent exact pixel center locations on the provided screenshot image.

Available Physical Actions:
1. "click": Click at center pixel coordinates (specify integer 'x' and 'y').
2. "type": Type text string (specify 'x' and 'y' to focus input box, and 'text' string to enter).
3. "key": Press a single keyboard key like 'Enter', 'Tab', 'Backspace', or 'Escape' (specify key name in 'text').
4. "scroll": Scroll page (specify 'direction': "up", "down", "left", "right").
5. "drag_and_drop": Click and drag from ('start_x', 'start_y') to ('end_x', 'end_y').
6. "wait": Pause 2 seconds for page or results to load.
7. "done": Declare that the objective is fully completed.

Output strictly valid JSON matching this schema:
{{
  "thought": "<detailed visual analysis of the screenshot identifying target buttons, inputs, text>",
  "action": "click" | "type" | "key" | "scroll" | "drag_and_drop" | "wait" | "done",
  "x": 640 or null,
  "y": 400 or null,
  "text": "search query" or null,
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
- Output strictly valid JSON.
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

        user_message = f"""Current Task Goal: "{goal}"

Current Page URL: {visual_state.get('current_url', 'N/A')}
Current Page Title: {visual_state.get('page_title', 'N/A')}
Viewport Dimensions: {vw}x{vh} pixels

Action History (Recent steps):
{history_summary}

Analyze the attached screenshot carefully. Determine the exact next visual action to execute.
Output strictly valid JSON.
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
                # Map reasoning for legacy compatibility
                result["reasoning"] = result.get("thought", "")
                logger.info(f"Visual Decision: Action={result['action']} | Coords=({result.get('x')}, {result.get('y')}) | Thought: {result['thought'][:60]}...")
                return result
            except ValidationError as ve:
                logger.warning(f"Pydantic Visual validation failed (attempt {attempt + 1}): {ve}")
                if attempt == max_retries:
                    raise RuntimeError(f"Visual action decision failed validation: {ve}") from ve
                user_message += f"\n\n[VALIDATION ERROR: {ve}. Please fix JSON schema output.]"
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

Analyze the current page state, goal, and past actions. Respond strictly in JSON format.
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
